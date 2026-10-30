"""
Task 15: scheduled report execution.

Honest scope note (documented here since it's worth being upfront about
rather than silently implying more than is built): this project has no
email/SMTP configuration anywhere (check app/config.py — there's no
mail server setting). So "recipients" are stored and shown in the UI as
who a schedule is *intended* for, and a scheduled run generates the
report and saves it to Report History exactly as a manual "Generate"
would — but no email is actually sent. Wiring real delivery up later is
a matter of adding SMTP settings and a `send_report_email()` call at the
end of `execute_schedule()` below; the generation side is already
complete and doesn't need to change.

Execution itself runs via APScheduler, in-process inside the FastAPI app
(see main.py) — this project has no Celery/Redis, so a lightweight
in-process scheduler that polls "what's due" once a minute is the right
amount of infrastructure for its size, consistent with how this app
already does on-read evaluation elsewhere (e.g. inventory alerts).
"""
import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import ReportSchedule, ReportStatus, ScheduleFrequency, Report, ReportFormat
from app.schemas.reports import ReportFilters
from app.services.reports import run_report_all_rows, render_csv, render_pdf, REPORT_NAMES, PDF_ROW_LIMIT
import base64


def compute_next_run(schedule: ReportSchedule, after: datetime) -> datetime:
    """Earliest run time strictly after `after` that matches the
    schedule's frequency/time/day config. All times are UTC."""
    hour, minute = divmod(schedule.execution_minute_utc, 60)

    if schedule.frequency == ScheduleFrequency.DAILY:
        candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= after:
            candidate += timedelta(days=1)
        return candidate

    if schedule.frequency == ScheduleFrequency.WEEKLY:
        target_dow = schedule.day_of_week or 0
        candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
        days_ahead = (target_dow - candidate.weekday()) % 7
        candidate += timedelta(days=days_ahead)
        if candidate <= after:
            candidate += timedelta(days=7)
        return candidate

    # MONTHLY
    target_dom = schedule.day_of_month or 1
    year, month = after.year, after.month
    candidate = after.replace(day=min(target_dom, 28), hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= after:
        month += 1
        if month > 12:
            month = 1
            year += 1
        candidate = candidate.replace(year=year, month=month)
    return candidate


def execute_schedule(db: Session, schedule: ReportSchedule) -> Report:
    """
    Generates the report a schedule describes, saves it as a Report
    History row (with the rendered file attached, same as a manual
    export would produce), and updates the schedule's last/next-run
    bookkeeping. Catches its own errors so one broken schedule can't take
    the scheduler loop down — see run_due_schedules in main.py.
    """
    filters = ReportFilters(**json.loads(schedule.filters_json))
    report = Report(
        company_id=schedule.company_id, generated_by=schedule.created_by, schedule_id=schedule.id,
        report_type=schedule.report_type, name=f"{schedule.name} (scheduled)",
        filters_json=schedule.filters_json, format=schedule.format, status=ReportStatus.PENDING,
    )
    db.add(report)
    db.flush()

    try:
        result = run_report_all_rows(db, schedule.company_id, schedule.report_type, filters, row_cap=PDF_ROW_LIMIT)
        title = REPORT_NAMES[schedule.report_type]

        if schedule.format == ReportFormat.PDF:
            file_bytes = render_pdf(title, result["columns"], result["rows"], filters)
        else:
            file_bytes = render_csv(result["columns"], result["rows"], filters).encode("utf-8")

        report.file_data = base64.b64encode(file_bytes).decode("ascii")
        report.row_count = result["total"]
        report.period_start = result["period_start"]
        report.period_end = result["period_end"]
        report.status = ReportStatus.COMPLETED
        report.completed_at = datetime.utcnow()
        run_status = ReportStatus.COMPLETED
    except Exception as exc:  # noqa: BLE001 — one bad schedule must not break the scheduler loop
        report.status = ReportStatus.FAILED
        report.error_message = str(exc)[:1000]
        report.completed_at = datetime.utcnow()
        run_status = ReportStatus.FAILED

    schedule.last_run_at = datetime.utcnow()
    schedule.last_run_status = run_status
    schedule.next_run_at = compute_next_run(schedule, datetime.utcnow())

    return report


def run_due_schedules(db: Session) -> int:
    """Called by the APScheduler job in main.py roughly once a minute.
    Runs every active schedule whose next_run_at has arrived."""
    now = datetime.utcnow()
    due = db.query(ReportSchedule).filter(
        ReportSchedule.is_active.is_(True), ReportSchedule.next_run_at <= now
    ).all()
    for schedule in due:
        execute_schedule(db, schedule)
    if due:
        db.commit()
    return len(due)
