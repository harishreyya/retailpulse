
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
import sqlalchemy as sa
import json

from app.database import get_db
from app.dependencies import get_current_company_id, get_current_user
from app.models import (
    User,
    AuditStatus,
    DataQualityIssue,
    ReconciliationRun,
    DataQualityIssueEvent,
)
from app.audit import log_action
from app.services.data_quality import execute_reconciliation
from datetime import datetime
from app.schemas.data_quality import DataQualityIssueStatusUpdate

router = APIRouter(
    prefix="/data-quality",
    tags=["data-quality"],
)


@router.post("/reconciliation/run")
def run_reconciliation(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    try:
        return execute_reconciliation(
            db=db,
            company_id=company_id,
            user_id=current_user.id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="The reconciliation run failed. Please check the backend logs.",
        ) from exc


@router.get("/issues")
def list_data_quality_issues(
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    module: str | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=200),
    issue_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    query = db.query(DataQualityIssue).filter(
        DataQualityIssue.company_id == company_id
    )

    if status_filter:
        query = query.filter(
            DataQualityIssue.status == status_filter.upper()
        )

    if severity:
        query = query.filter(
            DataQualityIssue.severity == severity.upper()
        )

    if module:
        query = query.filter(
            DataQualityIssue.module == module.upper()
        )  
    if issue_type:
        query = query.filter(
            DataQualityIssue.issue_type == issue_type.upper()
        )
    if date_from:
        query = query.filter(
            DataQualityIssue.detected_at >= date_from
        )

    if date_to:
        query = query.filter(
            DataQualityIssue.detected_at <= date_to
        )
    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            DataQualityIssue.description.ilike(search_term)
            | DataQualityIssue.record_label.ilike(search_term)
            | DataQualityIssue.id.cast(sa.String).ilike(search_term)
        )

    total = query.count()

    issues = (
        query.order_by(DataQualityIssue.detected_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            {
                "id": str(issue.id),
                "issue_type": issue.issue_type,
                "severity": issue.severity,
                "module": issue.module,
                "record_type": issue.record_type,
                "record_id": issue.record_id,
                "record_label": issue.record_label,
                "description": issue.description,
                "details": issue.details_json,
                "status": issue.status,
                "detected_at": issue.detected_at,
                "last_detected_at": issue.last_detected_at,
                "resolved_at": issue.resolved_at,
                "resolution_note": issue.resolution_note,
            }
            for issue in issues
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/reconciliation/runs")
def list_reconciliation_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    query = db.query(ReconciliationRun).filter(
        ReconciliationRun.company_id == company_id
    )

    total = query.count()

    runs = (
        query.order_by(ReconciliationRun.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            {
                "id": str(run.id),
                "triggered_by": str(run.triggered_by) if run.triggered_by else None,
                "triggered_by_name": run.trigger_user.name if run.trigger_user else "System",
                "status": run.status,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "records_checked": run.records_checked,
                "issues_detected": run.issues_detected,
                "issues_resolved": run.issues_resolved,
                "failed_checks": run.failed_checks,
                "summary": (
                           json.loads(run.summary_json)
                           if run.summary_json
                           else None
                           ),
                "error_message": run.error_message,
            }
            for run in runs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/issues/{issue_id}")
def get_data_quality_issue_detail(
    issue_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    issue = (
        db.query(DataQualityIssue)
        .filter(
            DataQualityIssue.id == issue_id,
            DataQualityIssue.company_id == company_id,
        )
        .one_or_none()
    )

    if issue is None:
        raise HTTPException(
            status_code=404,
            detail="Data-quality issue not found.",
        )

    events = (
        db.query(DataQualityIssueEvent)
        .filter(
            DataQualityIssueEvent.issue_id == issue.id,
            DataQualityIssueEvent.company_id == company_id,
        )
        .order_by(DataQualityIssueEvent.created_at.asc())
        .all()
    )

    return {
        "id": str(issue.id),
        "issue_type": issue.issue_type,
        "severity": issue.severity,
        "module": issue.module,
        "record_type": issue.record_type,
        "record_id": issue.record_id,
        "record_label": issue.record_label,
        "description": issue.description,
        "details": issue.details_json,
        "status": issue.status,
        "detected_at": issue.detected_at,
        "last_detected_at": issue.last_detected_at,
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
        "resolved_at": issue.resolved_at,
        "resolved_by": str(issue.resolved_by) if issue.resolved_by else None,
        "resolution_note": issue.resolution_note,
        "history": [
    {
        "id": str(event.id),
        "user_id": str(event.user_id) if event.user_id else None,
        "user_name": event.user.name if event.user else "System",
        "previous_status": event.previous_status,
        "new_status": event.new_status,
        "note": event.note,
        "created_at": event.created_at,
    }
    for event in events
],
    }

@router.patch("/issues/{issue_id}/status")
def update_data_quality_issue_status(
    issue_id: str,
    request: Request,
    payload: DataQualityIssueStatusUpdate,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    new_status = payload.status
    note = payload.note

    issue = (
        db.query(DataQualityIssue)
        .filter(
            DataQualityIssue.id == issue_id,
            DataQualityIssue.company_id == company_id,
        )
        .one_or_none()
    )

    if issue is None:
        raise HTTPException(
            status_code=404,
            detail="Data-quality issue not found.",
        )

    previous_status = issue.status

    try:
        issue.status = new_status

        if new_status == "RESOLVED":
            issue.resolved_at = datetime.utcnow()
            issue.resolved_by = current_user.id
            issue.resolution_note = note
        else:
            issue.resolved_at = None
            issue.resolved_by = None
            issue.resolution_note = None

        event = DataQualityIssueEvent(
            company_id=company_id,
            issue_id=issue.id,
            user_id=current_user.id,
            previous_status=previous_status,
            new_status=new_status,
            note=note,
        )

        db.add(event)

        log_action(
            db=db,
            request=request,
            action="Data Quality Issue Status Updated",
            company_id=company_id,
            user_id=current_user.id,
            entity_name="Data Quality Issue",
            details=(
                f"Issue {issue_id}: {previous_status} -> {new_status}. "
                f"Note: {note or 'No note provided'}"
            ),
            resource_type="DataQualityIssue",
            resource_id=issue_id,
            status=AuditStatus.SUCCESS,
            before={"status": previous_status},
            after={
                "status": new_status,
                "resolution_note": note,
            },
        )

        db.commit()
        db.refresh(issue)

        return {
            "id": str(issue.id),
            "status": issue.status,
            "resolved_at": issue.resolved_at,
            "resolution_note": issue.resolution_note,
            "message": "Issue status updated successfully.",
        }

    except Exception:
        db.rollback()
        raise