import base64
import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_roles, get_current_company_id
from app.audit import log_action
from app.models import (
    User, UserRole, Report, ReportType, ReportFormat, ReportStatus,
    Category, Customer, Product,
)
from app.schemas.reports import (
    ReportGenerateRequest, ReportGenerateResponse, ReportHistoryRow, ReportHistoryListResponse,
    ReportFilterOptions, ReportFilters,
)
from app.services import reports as report_service

router = APIRouter(prefix="/reports", tags=["reports"])

REPORT_ROLES = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST]


def _filters_to_json(filters: ReportFilters) -> str:
    return json.dumps(filters.model_dump(mode="json"))


@router.get("/filter-options", response_model=ReportFilterOptions)
def filter_options(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(REPORT_ROLES)),
):
    categories = db.query(Category.id, Category.name).filter(Category.company_id == company_id).all()
    brands = [
        b for (b,) in db.query(Product.brand).filter(
            Product.company_id == company_id, Product.brand.isnot(None)
        ).distinct().order_by(Product.brand.asc()).all()
    ]
    customers = db.query(Customer.id, Customer.full_name).filter(
        Customer.company_id == company_id, Customer.is_deleted.is_(False)
    ).order_by(Customer.full_name.asc()).limit(500).all()

    return ReportFilterOptions(
        categories=[{"id": c.id, "name": c.name} for c in categories],
        brands=brands,
        customers=[{"id": c.id, "name": c.full_name} for c in customers],
    )


@router.post("/generate", response_model=ReportGenerateResponse)
def generate_report(
    payload: ReportGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(REPORT_ROLES)),
):
    report = Report(
        company_id=company_id, generated_by=current_user.id, report_type=payload.report_type,
        name=report_service.REPORT_NAMES[payload.report_type], filters_json=_filters_to_json(payload.filters),
        format=ReportFormat.NONE, status=ReportStatus.PENDING,
    )
    db.add(report)
    db.flush()

    try:
        result = report_service.run_report(
            db, company_id, payload.report_type, payload.filters,
            sort_by=payload.sort_by, sort_dir=payload.sort_dir, page=payload.page, page_size=payload.page_size,
        )
        report.status = ReportStatus.COMPLETED
        report.row_count = result["total"]
        report.period_start = result["period_start"]
        report.period_end = result["period_end"]
        report.completed_at = datetime.utcnow()
    except Exception as exc:
        report.status = ReportStatus.FAILED
        report.error_message = str(exc)[:1000]
        report.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=400, detail=f"Could not generate report: {exc}")

    log_action(db, request, "Report Generated", company_id=company_id, user_id=current_user.id,
               resource_type="Report", resource_id=report.id, entity_name=report.name,
               details=f"type={payload.report_type.value}, rows={result['total']}")
    db.commit()

    return ReportGenerateResponse(
        report_id=report.id, report_type=payload.report_type, name=report.name,
        columns=result["columns"], rows=result["rows"], total=result["total"],
        page=payload.page, page_size=payload.page_size, filters=payload.filters,
        period_start=result["period_start"], period_end=result["period_end"],
        generated_at=report.created_at,
    )


@router.get("/history", response_model=ReportHistoryListResponse)
def report_history(
    report_type: Optional[ReportType] = None,
    status_filter: Optional[ReportStatus] = Query(None, alias="status"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(REPORT_ROLES)),
):
    query = db.query(Report).options(joinedload(Report.generator)).filter(Report.company_id == company_id)
    if report_type:
        query = query.filter(Report.report_type == report_type)
    if status_filter:
        query = query.filter(Report.status == status_filter)
    if date_from:
        query = query.filter(Report.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Report.created_at <= datetime.combine(date_to, datetime.max.time()))

    total = query.count()
    rows = query.order_by(Report.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = [
        ReportHistoryRow(
            id=r.id, report_type=r.report_type, name=r.name,
            generated_by_name=r.generator.name if r.generator else ("Scheduled" if r.schedule_id else None),
            filters=ReportFilters(**json.loads(r.filters_json)), format=r.format, status=r.status,
            error_message=r.error_message, row_count=r.row_count, schedule_id=r.schedule_id,
            created_at=r.created_at, completed_at=r.completed_at,
        )
        for r in rows
    ]
    return ReportHistoryListResponse(items=items, total=total, page=page, page_size=page_size)


def _get_report_or_404(db: Session, company_id: str, report_id: str) -> Report:
    report = db.query(Report).filter(Report.id == report_id, Report.company_id == company_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/{report_id}", response_model=ReportGenerateResponse)
def get_report(
    report_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(REPORT_ROLES)),
):
    """Re-runs the report's stored filters live (data may have changed
    since it was first generated) rather than needing to have cached
    every row — History only needs to remember WHAT was run, not every
    row that came back, except for the export file itself (see below)."""
    report = _get_report_or_404(db, company_id, report_id)
    filters = ReportFilters(**json.loads(report.filters_json))
    result = report_service.run_report(db, company_id, report.report_type, filters, page=page, page_size=page_size)
    return ReportGenerateResponse(
        report_id=report.id, report_type=report.report_type, name=report.name,
        columns=result["columns"], rows=result["rows"], total=result["total"],
        page=page, page_size=page_size, filters=filters,
        period_start=result["period_start"], period_end=result["period_end"],
        generated_at=report.created_at,
    )


@router.get("/{report_id}/export")
def export_report(
    report_id: str,
    format: str = Query(..., pattern="^(csv|pdf)$"),
    request: Request = None,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(REPORT_ROLES)),
):
    report = _get_report_or_404(db, company_id, report_id)
    filters = ReportFilters(**json.loads(report.filters_json))

    result = report_service.run_report_all_rows(
        db, company_id, report.report_type, filters, row_cap=report_service.PDF_ROW_LIMIT
    )
    title = report_service.REPORT_NAMES[report.report_type]

    if format == "csv":
        content = report_service.render_csv(result["columns"], result["rows"], filters)
        file_bytes = content.encode("utf-8")
        media_type, ext, fmt_enum = "text/csv", "csv", ReportFormat.CSV
    else:
        file_bytes = report_service.render_pdf(title, result["columns"], result["rows"], filters)
        media_type, ext, fmt_enum = "application/pdf", "pdf", ReportFormat.PDF

    # Persist what was exported onto the history row (so "download again"
    # from History returns the exact file, not a freshly-regenerated one).
    report.format = fmt_enum
    report.file_data = base64.b64encode(file_bytes).decode("ascii")
    report.row_count = result["total"]

    log_action(db, request, "Report Exported", company_id=company_id, user_id=current_user.id,
               resource_type="Report", resource_id=report.id, entity_name=report.name,
               details=f"format={format}, rows={result['total']}")
    db.commit()

    filename = f"{report.report_type.value.lower()}_report.{ext}"
    return StreamingResponse(
        iter([file_bytes]), media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{report_id}/download")
def download_saved_export(
    report_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(REPORT_ROLES)),
):
    """Re-downloads a previously generated export (manual or scheduled)
    exactly as it was produced, without re-running the query."""
    report = _get_report_or_404(db, company_id, report_id)
    if not report.file_data:
        raise HTTPException(status_code=404, detail="No export file is available for this report")

    file_bytes = base64.b64decode(report.file_data)
    media_type = "application/pdf" if report.format == ReportFormat.PDF else "text/csv"
    ext = "pdf" if report.format == ReportFormat.PDF else "csv"
    filename = f"{report.report_type.value.lower()}_report.{ext}"
    return StreamingResponse(
        iter([file_bytes]), media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
