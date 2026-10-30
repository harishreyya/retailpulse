import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_roles, get_current_company_id
from app.audit import log_action
from app.models import User, UserRole, ReportSchedule, AuditStatus
from app.schemas.reports import (
    ReportScheduleCreate, ReportScheduleUpdate, ReportScheduleOut, ReportScheduleListResponse, ReportFilters,
)
from app.services.report_schedules import compute_next_run, execute_schedule

router = APIRouter(prefix="/report-schedules", tags=["report-schedules"])

# Scheduling recurring reports (which can include customer/sales data) is
# kept Admin-only — Analysts can generate ad-hoc reports (see reports.py)
# but not set up unattended recurring exports.
SCHEDULE_ROLES = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN]


def _time_to_minutes(execution_time: str) -> int:
    hour, minute = execution_time.split(":")
    return int(hour) * 60 + int(minute)


def _minutes_to_time(minutes: int) -> str:
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def _validate_day_fields(payload) -> None:
    if payload.frequency == "WEEKLY" and payload.day_of_week is None:
        raise HTTPException(status_code=400, detail="day_of_week is required for a WEEKLY schedule")
    if payload.frequency == "MONTHLY" and payload.day_of_month is None:
        raise HTTPException(status_code=400, detail="day_of_month is required for a MONTHLY schedule")


def _to_out(s: ReportSchedule) -> ReportScheduleOut:
    return ReportScheduleOut(
        id=s.id, name=s.name, report_type=s.report_type, filters=ReportFilters(**json.loads(s.filters_json)),
        format=s.format, frequency=s.frequency, execution_time=_minutes_to_time(s.execution_minute_utc),
        day_of_week=s.day_of_week, day_of_month=s.day_of_month, recipients=json.loads(s.recipients_json),
        is_active=s.is_active, created_by_name=s.creator.name if s.creator else None,
        last_run_at=s.last_run_at, last_run_status=s.last_run_status, next_run_at=s.next_run_at,
        created_at=s.created_at,
    )


def _get_or_404(db: Session, company_id: str, schedule_id: str) -> ReportSchedule:
    s = db.query(ReportSchedule).filter(
        ReportSchedule.id == schedule_id, ReportSchedule.company_id == company_id
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return s


@router.get("", response_model=ReportScheduleListResponse)
def list_schedules(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SCHEDULE_ROLES)),
):
    rows = db.query(ReportSchedule).options(joinedload(ReportSchedule.creator)).filter(
        ReportSchedule.company_id == company_id
    ).order_by(ReportSchedule.created_at.desc()).all()
    return ReportScheduleListResponse(items=[_to_out(s) for s in rows], total=len(rows))


@router.post("", response_model=ReportScheduleOut, status_code=201)
def create_schedule(
    payload: ReportScheduleCreate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SCHEDULE_ROLES)),
):
    _validate_day_fields(payload)

    schedule = ReportSchedule(
        company_id=company_id, created_by=current_user.id, name=payload.name,
        report_type=payload.report_type, filters_json=json.dumps(payload.filters.model_dump(mode="json")),
        format=payload.format, frequency=payload.frequency,
        execution_minute_utc=_time_to_minutes(payload.execution_time),
        day_of_week=payload.day_of_week, day_of_month=payload.day_of_month,
        recipients_json=json.dumps(payload.recipients), is_active=payload.is_active,
    )
    db.add(schedule)
    db.flush()
    schedule.next_run_at = compute_next_run(schedule, datetime.utcnow())

    log_action(db, request, "Report Schedule Created", company_id=company_id, user_id=current_user.id,
               resource_type="ReportSchedule", resource_id=schedule.id, entity_name=schedule.name)
    db.commit()
    db.refresh(schedule)
    return _to_out(schedule)


@router.put("/{schedule_id}", response_model=ReportScheduleOut)
def update_schedule(
    schedule_id: str,
    payload: ReportScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SCHEDULE_ROLES)),
):
    schedule = _get_or_404(db, company_id, schedule_id)
    update_data = payload.model_dump(exclude_unset=True)
    before_snapshot = {}
    after_snapshot = {}

    if "name" in update_data:
        before_snapshot["name"], after_snapshot["name"] = schedule.name, update_data["name"]
        schedule.name = update_data["name"]
    if "filters" in update_data:
        schedule.filters_json = json.dumps(payload.filters.model_dump(mode="json"))
    if "format" in update_data:
        schedule.format = update_data["format"]
    if "frequency" in update_data:
        before_snapshot["frequency"], after_snapshot["frequency"] = schedule.frequency.value, update_data["frequency"]
        schedule.frequency = update_data["frequency"]
    if "execution_time" in update_data:
        schedule.execution_minute_utc = _time_to_minutes(update_data["execution_time"])
    if "day_of_week" in update_data:
        schedule.day_of_week = update_data["day_of_week"]
    if "day_of_month" in update_data:
        schedule.day_of_month = update_data["day_of_month"]
    if "recipients" in update_data:
        schedule.recipients_json = json.dumps([str(r) for r in update_data["recipients"]])
    if "is_active" in update_data:
        before_snapshot["is_active"], after_snapshot["is_active"] = schedule.is_active, update_data["is_active"]
        schedule.is_active = update_data["is_active"]

    # Re-validate day-of-week/month requirements against the schedule's
    # FINAL state (covers both "frequency changed" and "frequency stayed
    # WEEKLY/MONTHLY but day field was cleared").
    if schedule.frequency == "WEEKLY" and schedule.day_of_week is None:
        raise HTTPException(status_code=400, detail="day_of_week is required for a WEEKLY schedule")
    if schedule.frequency == "MONTHLY" and schedule.day_of_month is None:
        raise HTTPException(status_code=400, detail="day_of_month is required for a MONTHLY schedule")

    schedule.next_run_at = compute_next_run(schedule, datetime.utcnow())

    log_action(db, request, "Report Schedule Updated", company_id=company_id, user_id=current_user.id,
               resource_type="ReportSchedule", resource_id=schedule.id, entity_name=schedule.name,
               before=before_snapshot or None, after=after_snapshot or None)
    db.commit()
    db.refresh(schedule)
    return _to_out(schedule)


@router.patch("/{schedule_id}/toggle", response_model=ReportScheduleOut)
def toggle_schedule(
    schedule_id: str,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SCHEDULE_ROLES)),
):
    schedule = _get_or_404(db, company_id, schedule_id)
    was_active = schedule.is_active
    schedule.is_active = not schedule.is_active
    if schedule.is_active:
        schedule.next_run_at = compute_next_run(schedule, datetime.utcnow())

    log_action(db, request, "Report Schedule Updated", company_id=company_id, user_id=current_user.id,
               resource_type="ReportSchedule", resource_id=schedule.id, entity_name=schedule.name,
               before={"is_active": was_active}, after={"is_active": schedule.is_active})
    db.commit()
    db.refresh(schedule)
    return _to_out(schedule)


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: str,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SCHEDULE_ROLES)),
):
    schedule = _get_or_404(db, company_id, schedule_id)
    name = schedule.name
    db.delete(schedule)
    log_action(db, request, "Report Schedule Deleted", company_id=company_id, user_id=current_user.id,
               resource_type="ReportSchedule", resource_id=schedule_id, entity_name=name)
    db.commit()
    return None


@router.post("/{schedule_id}/run-now", status_code=202)
def run_schedule_now(
    schedule_id: str,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SCHEDULE_ROLES)),
):
    """Runs a schedule immediately, outside its normal cadence — useful
    for testing a schedule's filters/format without waiting for the
    actual scheduled time. Uses the same execute_schedule() the real
    poller uses, so this also updates last_run_at/next_run_at exactly as
    a normal scheduled run would."""
    schedule = _get_or_404(db, company_id, schedule_id)
    report = execute_schedule(db, schedule)
    log_action(db, request, "Report Schedule Run Manually", company_id=company_id, user_id=current_user.id,
               resource_type="ReportSchedule", resource_id=schedule.id, entity_name=schedule.name,
               status=AuditStatus.SUCCESS if report.status.value == "COMPLETED" else AuditStatus.FAILED)
    db.commit()
    return {"report_id": report.id, "status": report.status.value}
