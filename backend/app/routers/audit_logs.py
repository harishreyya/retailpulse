import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles, get_current_company_id
from app.audit import log_action
from app.models import User, UserRole, AuditStatus, AuditLog
from app.schemas import AuditLogRow, AuditLogDetail, AuditLogListResponse, AuditLogFilterOptions
from app.services import audit_logs as audit_service

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])

# Task 14-style enforcement, mirrored here per Task 13's "Admin-Only Access"
# requirement: only Admins may view, export, or clear audit logs. Frontend
# hides the nav item too, but that's cosmetic — this is what actually blocks it.
ADMIN_ONLY = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN]


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    status_filter: Optional[AuditStatus] = Query(None, alias="status"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    rows, total = audit_service.list_audit_logs(
        db, company_id, user_id=user_id, action=action, resource_type=resource_type,
        status=status_filter, date_from=date_from, date_to=date_to, search=search,
        sort_dir=sort_dir, page=page, page_size=page_size,
    )
    return AuditLogListResponse(
        items=[AuditLogRow(**audit_service.serialize_row(r)) for r in rows],
        total=total, page=page, page_size=page_size,
    )


@router.get("/filter-options", response_model=AuditLogFilterOptions)
def get_filter_options(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    return AuditLogFilterOptions(**audit_service.get_filter_options(db, company_id))


@router.get("/export")
def export_audit_logs(
    format: str = Query(..., pattern="^(csv|pdf)$"),
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    status_filter: Optional[AuditStatus] = Query(None, alias="status"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    request: Request = None,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    filter_kwargs = dict(
        user_id=user_id, action=action, resource_type=resource_type,
        status=status_filter, date_from=date_from, date_to=date_to, search=search,
    )
    total = audit_service.count_audit_logs(db, company_id, **filter_kwargs)

    log_action(db, request, "Audit Logs Exported", company_id=company_id, user_id=current_user.id,
               resource_type="AuditLog", status=AuditStatus.SUCCESS, details=f"format={format}, count={total}")
    db.commit()

    headers = ["Timestamp", "User", "Action", "Resource Type", "Resource ID", "Description", "IP Address", "Status"]

    def _row_values(r):
        return [
            r.timestamp.isoformat(), r.user.name if r.user else "System", r.action,
            r.resource_type or "", r.resource_id or "", r.details or "", r.ip_address or "", r.status.value,
        ]

    if format == "csv":
        def generate_csv():
            class _Echo:
                def write(self, value):
                    return value
            writer = csv.writer(_Echo())
            yield writer.writerow(headers)
            for row in audit_service.iter_audit_logs_for_export(db, company_id, sort_dir=sort_dir, **filter_kwargs):
                yield writer.writerow(_row_values(row))

        return StreamingResponse(
            generate_csv(), media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
        )

    PDF_ROW_LIMIT = 5_000
    if total > PDF_ROW_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"PDF export supports up to {PDF_ROW_LIMIT:,} rows; this filter matches {total:,}. "
                    "Narrow the date range/filters, or use CSV export for the full set.",
        )
    data_rows = [_row_values(r) for r in audit_service.iter_audit_logs_for_export(db, company_id, sort_dir=sort_dir, **filter_kwargs)]

    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF export requires the 'reportlab' package.")

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    elements = [Paragraph("RetailPulse Audit Log Report", styles["Title"]), Spacer(1, 0.5 * cm)]
    table = Table([headers] + data_rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]))
    elements.append(table)
    doc.build(elements)
    pdf_buffer.seek(0)
    return StreamingResponse(
        pdf_buffer, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=audit_logs.pdf"},
    )


@router.delete("", status_code=status.HTTP_200_OK)
def clear_audit_logs(
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    """
    Admin-only, irreversible. The frontend requires a typed/explicit
    confirmation before ever calling this.

    Ordering guarantee: the DELETE runs and fully executes against the
    database FIRST, against whatever rows exist at that instant. Only
    AFTER that does the "Cleared" entry get created — a brand-new row
    that did not exist when the DELETE ran, so it cannot be one of the
    rows removed. Both the delete and the new row are then committed
    together: if anything raises before that commit, the whole thing
    rolls back, including the delete — the trail is never left partially
    wiped with no record of who did it.
    """
    try:
        deleted_count = audit_service.clear_audit_logs(db, company_id)
        entry = log_action(db, request, "Audit Logs Cleared", company_id=company_id, user_id=current_user.id,
                            resource_type="AuditLog", status=AuditStatus.SUCCESS,
                            details=f"{deleted_count} records cleared")
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to clear audit logs. No records were changed.")

    remaining = db.query(AuditLog).filter(AuditLog.company_id == company_id).count()
    return {"deleted_count": deleted_count, "remaining_count": remaining, "cleared_by_entry_id": entry.id}


@router.get("/{log_id}", response_model=AuditLogDetail)
def get_audit_log(
    log_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    entry = audit_service.get_audit_log(db, company_id, log_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return AuditLogDetail(**audit_service.serialize_detail(entry))
