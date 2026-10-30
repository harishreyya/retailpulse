"""
Task 13: Audit Logs & Activity Monitoring — business logic layer.

Kept separate from the router so the router stays a thin HTTP adapter:
parse request -> call service -> serialize response. Every function here
takes `company_id` as an explicit, required argument sourced by the
router from the authenticated session (never from a query param), which
is what actually enforces the tenant boundary this task calls for.
"""
import json
from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import or_, asc, desc
from sqlalchemy.orm import Session, joinedload

from app.models import AuditLog, AuditStatus, User


def _base_query(
    db: Session, company_id: str,
    user_id: Optional[str], action: Optional[str], resource_type: Optional[str],
    status: Optional[AuditStatus], date_from: Optional[date], date_to: Optional[date],
    search: Optional[str],
):
    query = db.query(AuditLog).options(joinedload(AuditLog.user)).filter(AuditLog.company_id == company_id)

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if status:
        query = query.filter(AuditLog.status == status)
    if date_from:
        query = query.filter(AuditLog.timestamp >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.filter(AuditLog.timestamp <= datetime.combine(date_to, time.max))

    if search:
        like = f"%{search}%"
        query = query.outerjoin(User, User.id == AuditLog.user_id).filter(
            or_(
                User.name.ilike(like),
                AuditLog.action.ilike(like),
                AuditLog.resource_type.ilike(like),
                AuditLog.resource_id.ilike(like),
                AuditLog.entity_name.ilike(like),
                AuditLog.details.ilike(like),
            )
        )

    return query


def list_audit_logs(
    db: Session, company_id: str,
    user_id: Optional[str] = None, action: Optional[str] = None, resource_type: Optional[str] = None,
    status: Optional[AuditStatus] = None, date_from: Optional[date] = None, date_to: Optional[date] = None,
    search: Optional[str] = None, sort_dir: str = "desc",
    page: int = 1, page_size: int = 25,
) -> tuple[list[AuditLog], int]:
    query = _base_query(db, company_id, user_id, action, resource_type, status, date_from, date_to, search)
    total = query.count()

    order_fn = asc if sort_dir == "asc" else desc
    rows = (
        query.order_by(order_fn(AuditLog.timestamp))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def count_audit_logs(
    db: Session, company_id: str,
    user_id: Optional[str] = None, action: Optional[str] = None, resource_type: Optional[str] = None,
    status: Optional[AuditStatus] = None, date_from: Optional[date] = None, date_to: Optional[date] = None,
    search: Optional[str] = None,
) -> int:
    return _base_query(db, company_id, user_id, action, resource_type, status, date_from, date_to, search).count()


def iter_audit_logs_for_export(
    db: Session, company_id: str,
    user_id: Optional[str] = None, action: Optional[str] = None, resource_type: Optional[str] = None,
    status: Optional[AuditStatus] = None, date_from: Optional[date] = None, date_to: Optional[date] = None,
    search: Optional[str] = None, sort_dir: str = "desc",
    chunk_size: int = 1000,
):
    """
    Yields matching rows in fixed-size chunks instead of the caller loading
    every matching row into one Python list at once (the previous approach
    used page_size=100_000, which for a company with a very large audit
    history would mean one massive result set materialized in memory for
    a single request). `yield_per` + `stream_results` streams results from
    the DB cursor in batches rather than buffering the whole query result,
    and the caller (the export endpoint) writes each row to the output
    stream as it arrives rather than waiting for the full set.
    """
    query = (
        _base_query(db, company_id, user_id, action, resource_type, status, date_from, date_to, search)
        .order_by(asc(AuditLog.timestamp) if sort_dir == "asc" else desc(AuditLog.timestamp))
        .execution_options(yield_per=chunk_size, stream_results=True)
    )
    for row in query:
        yield row


def get_audit_log(db: Session, company_id: str, log_id: str) -> Optional[AuditLog]:
    # company_id is part of the WHERE clause itself (not checked after the
    # fact), so a request for another company's log id simply matches
    # nothing rather than ever returning that company's data.
    return db.query(AuditLog).options(joinedload(AuditLog.user)).filter(
        AuditLog.id == log_id, AuditLog.company_id == company_id
    ).first()


def get_filter_options(db: Session, company_id: str) -> dict:
    users = (
        db.query(User.id, User.name)
        .join(AuditLog, AuditLog.user_id == User.id)
        .filter(AuditLog.company_id == company_id)
        .distinct()
        .order_by(User.name.asc())
        .all()
    )
    actions = [
        a for (a,) in db.query(AuditLog.action).filter(AuditLog.company_id == company_id).distinct().order_by(AuditLog.action.asc()).all()
    ]
    resource_types = [
        r for (r,) in db.query(AuditLog.resource_type).filter(
            AuditLog.company_id == company_id, AuditLog.resource_type.isnot(None)
        ).distinct().order_by(AuditLog.resource_type.asc()).all()
    ]
    return {
        "users": [{"id": uid, "name": name} for uid, name in users],
        "actions": actions,
        "resource_types": resource_types,
    }


def clear_audit_logs(db: Session, company_id: str) -> int:
    """Deletes every audit log row for this company only. Returns the
    count deleted. Caller is responsible for logging + committing the
    clearing action itself (done in the router, after this runs, so the
    "logs cleared" entry is the one thing left behind)."""
    count = db.query(AuditLog).filter(AuditLog.company_id == company_id).delete(synchronize_session=False)
    return count


def serialize_row(entry: AuditLog) -> dict:
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "user_name": entry.user.name if entry.user else None,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "entity_name": entry.entity_name,
        "description": entry.details,
        "ip_address": entry.ip_address,
        "status": entry.status,
        "created_at": entry.timestamp,
    }


def serialize_detail(entry: AuditLog) -> dict:
    row = serialize_row(entry)
    row.update({
        "user_email": entry.user.email if entry.user else None,
        "user_agent": entry.browser,
        "before_values": json.loads(entry.before_values) if entry.before_values else None,
        "after_values": json.loads(entry.after_values) if entry.after_values else None,
    })
    return row
