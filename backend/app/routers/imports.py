import csv
from fileinput import filename
import io
import json
from datetime import datetime
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, Request, UploadFile,
    File, Form, Query, status, BackgroundTasks,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db, SessionLocal
from app.models import (
    User, UserRole, ImportJob, ImportError as ImportErrorRow,
    ImportType, ImportStatus, ImportRowStatus, NotificationType, NotificationPriority, AuditStatus,
)
from app.services.notifications import notify_roles, notify_user
from app.services.data_quality import run_targeted_data_quality_checks
from app.schemas import (
    ImportUploadResponse,
    ImportPreviewRow,
    ImportRowIssue,
    ImportValidationSummary,
    ImportJobOut,
    ImportJobListResponse,
    ImportJobDetailOut,
    ImportResultOut,
    ImportProgressOut,
    ImportCancelResponse,
    ImportErrorOut,
)
from app.dependencies import require_roles, get_current_company_id
from app.audit import log_action
from app.services import imports as import_service
from app.services.customers import recalculate_purchase_summary

router = APIRouter(prefix="/import", tags=["data-import"])

# Task 14: import functionality is Admin-only, front and back.
ADMIN_ONLY = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN]

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
PREVIEW_ROW_LIMIT = 10
MAX_ROW_ISSUES_RETURNED = 200  # keep the upload response small; full list via /errors


def _uploader_name(job: ImportJob) -> Optional[str]:
    return job.uploader.name if job.uploader else None


def _job_to_out(job: ImportJob) -> ImportJobOut:
    duration_seconds = None

    if job.started_at:
        end_time = job.completed_at or datetime.utcnow()
        duration_seconds = max(
            0,
            (end_time - job.started_at).total_seconds(),
        )

    return ImportJobOut(
        id=job.id,
        import_type=job.import_type,
        filename=job.filename,
        uploaded_by_name=_uploader_name(job),
        total_records=job.total_records,
        successful_records=job.successful_records,
        failed_records=job.failed_records,
        duplicate_records=job.duplicate_records,
        skipped_records=job.skipped_records,
        processed_records=job.processed_records,
        progress_percentage=job.progress_percentage,
        processing_stage=job.processing_stage,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=duration_seconds,
        cancellation_requested=job.cancellation_requested,
    )

def _get_job_or_404(db: Session, company_id: str, import_id: str) -> ImportJob:
    job = db.query(ImportJob).options(joinedload(ImportJob.uploader)).filter(
        ImportJob.id == import_id, ImportJob.company_id == company_id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


def _stage_validation(db: Session, job: ImportJob, results: list[import_service.RowResult]) -> ImportValidationSummary:
    """Clears any previously-stored row issues and re-stores the current
    validation pass, updating the job's counters."""
    db.query(ImportErrorRow).filter(ImportErrorRow.import_job_id == job.id).delete()

    valid = invalid = duplicate = 0
    for r in results:
        if r.status is None:
            valid += 1
            continue
        if r.status == ImportRowStatus.INVALID:
            invalid += 1
        elif r.status == ImportRowStatus.DUPLICATE:
            duplicate += 1
        db.add(ImportErrorRow(
            import_job_id=job.id,
            row_number=r.row_number,
            row_status=r.status,
            row_data=json.dumps(r.data),
            error_message=r.message,
        ))

    job.total_records = len(results)
    job.valid_records = valid
    job.invalid_records = invalid
    job.duplicate_records = duplicate
    job.status = ImportStatus.VALIDATED
    db.commit()
    db.refresh(job)
    return ImportValidationSummary(
        total_records=job.total_records, valid_records=valid,
        invalid_records=invalid, duplicate_records=duplicate,
    )


# Task 17: Download CSV import templates

IMPORT_TEMPLATES = {
    ImportType.PRODUCTS: {
        "headers": [
            "Product Name",
            "SKU",
            "Category",
            "Unit Price",
            "Stock Quantity",
            "Brand",
            "Description",
            "Cost Price",
            "Unit of Measure",
        ],
        "example": [
            "Sample Product",
            "SKU-001",
            "Electronics",
            "499",
            "10",
            "Sample Brand",
            "Sample product description",
            "300",
            "Piece",
        ],
    },
    ImportType.INVENTORY: {
        "headers": [
            "SKU",
            "Stock Quantity",
            "Reason",
            "Reorder Level",
            "Remarks",
        ],
        "example": [
            "SKU-001",
            "20",
            "Stock Adjustment",
            "5",
            "Initial stock update",
        ],
    },
    ImportType.CUSTOMERS: {
        "headers": [
            "Name",
            "Email",
            "Phone",
            "Address",
            "City",
            "State",
            "Country",
            "Postal Code",
            "Customer Type",
        ],
        "example": [
            "John Doe",
            "john@example.com",
            "9876543210",
            "123 Sample Street",
            "Hyderabad",
            "Telangana",
            "India",
            "500001",
            "RETAIL",
        ],
    },
    ImportType.SALES: {
        "headers": [
            "Customer",
            "Product",
            "Quantity",
            "Unit Price",
            "Sale Date",
            "Invoice Number",
            "Sales Channel",
            "Payment Method",
        ],
        "example": [
            "john@example.com",
            "SKU-001",
            "2",
            "499",
            "2026-11-07",
            "INV-001",
            "Retail",
            "UPI",
        ],
    },
}


@router.get("/templates/{import_type}")
def download_import_template(
    import_type: ImportType,
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    """Download a CSV template for the selected import type."""

    template = IMPORT_TEMPLATES.get(import_type)

    if not template:
        raise HTTPException(
            status_code=400,
            detail="Unsupported import type",
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(template["headers"])
    writer.writerow(template["example"])

    filename = f"{import_type.value.lower()}_import_template.csv"

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )

@router.post("/upload", response_model=ImportUploadResponse)
async def upload_import(
    request: Request,
    import_type: ImportType = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    filename = file.filename or ""

    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only .csv files are supported",
        )

    raw_bytes = await file.read()
    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File is too large (max 10 MB)")
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")

    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded CSV")

    parsed = import_service.parse_csv_text(text)
    if not parsed.fieldnames:
        raise HTTPException(status_code=400, detail="Could not read a header row from this CSV")

    missing = import_service.missing_required_columns(import_type, parsed.fieldnames)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required column(s) for {import_type.value.title()}: {', '.join(missing)}",
        )
    if not parsed.rows:
        raise HTTPException(status_code=400, detail="The CSV has a header row but no data rows")

    job = ImportJob(
        company_id=company_id,
        import_type=import_type,
        filename=filename,
        uploaded_by=current_user.id,
        raw_content=text,
        total_records=len(parsed.rows),
        status=ImportStatus.PENDING,
    )
    db.add(job)
    db.flush()

    results = import_service.validate_rows(db, company_id, import_type, parsed)
    summary = _stage_validation(db, job, results)

    log_action(
    db,
    request,
    "Import Uploaded",
    company_id=company_id,
    user_id=current_user.id,
    entity_name=job.filename,
    resource_type="ImportJob",
    resource_id=job.id,
        details=(
        f"{import_type.value}: "
        f"{summary.total_records} rows uploaded and validated."
    ),
)
    db.commit()

    preview_rows = [ImportPreviewRow(row_number=r.row_number, data=r.data) for r in results[:PREVIEW_ROW_LIMIT]]
    row_issues = [
        ImportRowIssue(row_number=r.row_number, status=r.status, message=r.message, data=r.data)
        for r in results if r.status is not None
    ][:MAX_ROW_ISSUES_RETURNED]

    return ImportUploadResponse(
        import_id=job.id,
        import_type=import_type,
        filename=job.filename,
        status=job.status,
        detected_columns=parsed.fieldnames,
        missing_columns=[],
        preview_rows=preview_rows,
        summary=summary,
        row_issues=row_issues,
    )


@router.post("/{import_id}/validate", response_model=ImportUploadResponse)
def revalidate_import(
    import_id: str,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    """
    Re-runs column + row validation against the currently staged CSV.
    Useful if the Admin fixed conflicting data (e.g. added a missing
    product) between uploading and processing.
    """
    job = _get_job_or_404(db, company_id, import_id)
    if job.status in (ImportStatus.COMPLETED, ImportStatus.COMPLETED_WITH_ERRORS, ImportStatus.PROCESSING):
        raise HTTPException(status_code=400, detail=f"Import is already {job.status.value.lower()} and cannot be re-validated")

    parsed = import_service.parse_csv_text(job.raw_content)
    results = import_service.validate_rows(db, company_id, job.import_type, parsed)
    summary = _stage_validation(db, job, results)

    preview_rows = [ImportPreviewRow(row_number=r.row_number, data=r.data) for r in results[:PREVIEW_ROW_LIMIT]]
    row_issues = [
        ImportRowIssue(row_number=r.row_number, status=r.status, message=r.message, data=r.data)
        for r in results if r.status is not None
    ][:MAX_ROW_ISSUES_RETURNED]

    return ImportUploadResponse(
        import_id=job.id,
        import_type=job.import_type,
        filename=job.filename,
        status=job.status,
        detected_columns=parsed.fieldnames,
        missing_columns=[],
        preview_rows=preview_rows,
        summary=summary,
        row_issues=row_issues,
    )



@router.post("/{import_id}/process", response_model=ImportResultOut)
def process_import(
    import_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    job = _get_job_or_404(db, company_id, import_id)

    if job.status in (
        ImportStatus.COMPLETED,
        ImportStatus.COMPLETED_WITH_ERRORS,
        ImportStatus.PROCESSING,
        ImportStatus.CANCELLED,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Import is already {job.status.value.lower()}",
        )

    now = datetime.utcnow()

    job.status = ImportStatus.PROCESSING
    job.started_at = now
    job.completed_at = None
    job.processed_records = 0
    job.successful_records = 0
    job.failed_records = 0
    job.duplicate_records = 0
    job.skipped_records = 0
    job.progress_percentage = 0
    job.processing_stage = "STARTING"
    job.cancellation_requested = False

    log_action(
        db,
        request,
        "Import Started",
        company_id=company_id,
        user_id=current_user.id,
        entity_name=job.filename,
        resource_type="ImportJob",
        resource_id=job.id,
        details=f"{job.import_type.value}: background processing started.",
    )

    db.commit()

    # Task 17: Notify administrators that import processing has started.
    notify_roles(
        db,
        company_id,
        NotificationType.IMPORT_STARTED,
        title="Import Started",
        message=(
            f"{job.import_type.value.title()} import "
            f"'{job.filename}' has started processing."
        ),
        priority=NotificationPriority.LOW,
        resource_type="ImportJob",
        resource_id=job.id,
        dedupe_key=f"import-started:{job.id}",
    )
    db.commit()

    # The worker creates its own database session.
    background_tasks.add_task(
        _run_processing_background,
        job.id,
        company_id,
        current_user.id,
        request,
    )

    return ImportResultOut(
        id=job.id,
        status=ImportStatus.PROCESSING,
        total_records=job.total_records,
        successful_records=0,
        failed_records=0,
        duplicate_records=0,
        completed_at=None,
    )


def _checks_for_import_type(import_type: ImportType) -> list[str]:
    checks = {
        ImportType.PRODUCTS: [
            "products",
            "inventory",
            "stock_movements",
        ],
        ImportType.INVENTORY: [
            "inventory",
            "stock_movements",
        ],
        ImportType.CUSTOMERS: [
            "customers",
            "customer_purchase_summaries",
        ],
        ImportType.SALES: [
            "sales",
            "sales_references",
            "sale_stock_movements",
            "customer_purchase_summaries",
        ],
    }
    return checks[import_type]


def _run_processing_background(
    import_id: str,
    company_id: str,
    user_id: str,
    request: Request,
):
    db = SessionLocal()

    try:
        job = _get_job_or_404(db, company_id, import_id)

        if job.status != ImportStatus.PROCESSING:
            return

        _run_processing(db, job, company_id, user_id, request)

    except Exception:
        db.rollback()

        job = db.query(ImportJob).filter(
            ImportJob.id == import_id,
            ImportJob.company_id == company_id,
        ).one_or_none()

        if job and job.status == ImportStatus.PROCESSING:
            job.status = ImportStatus.FAILED
            job.completed_at = datetime.utcnow()
            job.processing_stage = "FAILED"

            notify_roles(
                db,
                company_id,
                NotificationType.IMPORT_FAILED,
                title="Import Failed",
                message=(
                    f"{job.import_type.value.title()} import "
                    f"'{job.filename}' failed. "
                    f"{job.successful_records} records were successfully imported "
                    f"before the failure."
                ),
                priority=NotificationPriority.HIGH,
                resource_type="ImportJob",
                resource_id=job.id,
                dedupe_key=f"import-failed:{job.id}",
            )

            log_action(
                db,
                request,
                "Import Failed",
                company_id=company_id,
                user_id=user_id,
                entity_name=job.filename,
                resource_type="ImportJob",
                resource_id=job.id,
                status=AuditStatus.FAILED,
                details=(
                    f"Background import failed. "
                    f"{job.successful_records} records were committed."
                ),
            )

            db.commit()

    finally:
        db.close()


def _run_processing(
    db: Session,
    job: ImportJob,
    company_id: str,
    user_id: str,
    request: Request,
) -> ImportResultOut:

    parsed = import_service.parse_csv_text(job.raw_content)

    results = import_service.validate_rows(
        db,
        company_id,
        job.import_type,
        parsed,
    )

    header_map = import_service.header_map(parsed.fieldnames)

    db.query(ImportErrorRow).filter(
        ImportErrorRow.import_job_id == job.id
    ).delete()

    db.commit()

    successful = 0
    failed = 0
    duplicate = 0
    processed = 0
    skipped = 0

    job.total_records = len(results)
    job.processing_stage = "PROCESSING_ROWS"
    db.commit()

    for r in results:
        # Refresh to detect cancellation requested by another API request.
        db.refresh(job)

        if job.cancellation_requested:
            job.status = ImportStatus.CANCELLED
            job.completed_at = datetime.utcnow()
            job.processing_stage = "CANCELLED"
            job.processed_records = processed
            job.successful_records = successful
            job.failed_records = failed
            job.duplicate_records = duplicate
            job.skipped_records = skipped
            job.valid_records = successful
            job.invalid_records = failed
            job.progress_percentage = int(
                processed / max(len(results), 1) * 100
            )
            db.commit()
            break

        if r.status == ImportRowStatus.INVALID:
            failed += 1
            skipped += 1

            db.add(
                ImportErrorRow(
                    import_job_id=job.id,
                    row_number=r.row_number,
                    row_status=ImportRowStatus.INVALID,
                    row_data=json.dumps(r.data),
                    error_message=r.message,
                )
            )

        elif r.status == ImportRowStatus.DUPLICATE:
            duplicate += 1
            skipped += 1

            db.add(
                ImportErrorRow(
                    import_job_id=job.id,
                    row_number=r.row_number,
                    row_status=ImportRowStatus.DUPLICATE,
                    row_data=json.dumps(r.data),
                    error_message=r.message,
                )
            )

        else:
            savepoint = db.begin_nested()

            try:
                if job.import_type == ImportType.PRODUCTS:
                    import_service.process_product_row(
                        db, company_id, r.data, header_map
                    )

                elif job.import_type == ImportType.INVENTORY:
                    import_service.process_inventory_row(
                        db, company_id, r.data, header_map, user_id
                    )

                elif job.import_type == ImportType.CUSTOMERS:
                    import_service.process_customer_row(
                        db, company_id, r.data, header_map, user_id
                    )

                elif job.import_type == ImportType.SALES:
                    sale = import_service.process_sale_row(
                        db, company_id, r.data, header_map, user_id
                    )
                    db.flush()
                    recalculate_purchase_summary(db, sale.customer_id)

                else:
                    raise ValueError("Unsupported import type")

                savepoint.commit()
                successful += 1

            except Exception:
                savepoint.rollback()
                failed += 1

                # Never expose raw database exceptions or stack details.
                db.add(
                    ImportErrorRow(
                        import_job_id=job.id,
                        row_number=r.row_number,
                        row_status=ImportRowStatus.FAILED,
                        row_data=json.dumps(r.data),
                        error_message=(
                            "This row could not be imported. "
                            "Check its values and related records."
                        ),
                    )
                )

        processed += 1

        job.processed_records = processed
        job.successful_records = successful
        job.failed_records = failed
        job.duplicate_records = duplicate
        job.skipped_records = skipped
        job.valid_records = successful
        job.invalid_records = failed
        job.progress_percentage = int(
            processed / max(len(results), 1) * 100
        )

        # Persist progress and this row's result.
        db.commit()

    db.refresh(job)

    # Do not overwrite a cancellation result with COMPLETED.
    if job.status == ImportStatus.CANCELLED:
        log_action(
            db,
            request,
            "Import Cancelled",
            company_id=company_id,
            user_id=user_id,
            entity_name=job.filename,
            resource_type="ImportJob",
            resource_id=job.id,
            details=(
                f"{successful} succeeded, {failed} failed, "
                f"{duplicate} duplicates before cancellation."
            ),
        )
        db.commit()

        return ImportResultOut(
            id=job.id,
            status=job.status,
            total_records=job.total_records,
            successful_records=successful,
            failed_records=failed,
            duplicate_records=duplicate,
            completed_at=job.completed_at,
        )

    # Run relevant Data Quality checks after processing.
    job.processing_stage = "DATA_QUALITY_CHECKS"
    db.commit()

    try:
        run_targeted_data_quality_checks(
            db,
            company_id,
            _checks_for_import_type(job.import_type),
        )
        db.commit()
    except Exception:
        # A reconciliation warning must not undo already-imported records.
        db.rollback()
        job = _get_job_or_404(db, company_id, job.id)
        job.processing_stage = "DATA_QUALITY_CHECK_WARNING"
        db.commit()

    job = _get_job_or_404(db, company_id, job.id)

    job.successful_records = successful
    job.failed_records = failed
    job.duplicate_records = duplicate
    job.skipped_records = skipped
    job.processed_records = processed
    job.valid_records = successful
    job.invalid_records = failed
    job.progress_percentage = 100
    job.completed_at = datetime.utcnow()
    job.processing_stage = "COMPLETED"

    job.status = (
        ImportStatus.COMPLETED
        if failed == 0 and duplicate == 0
        else ImportStatus.COMPLETED_WITH_ERRORS
    )

    notify_roles(
        db,
        company_id,
        NotificationType.IMPORT_COMPLETED,
        title=(
            "Import Completed"
            if job.status == ImportStatus.COMPLETED
            else "Import Completed With Errors"
        ),
        message=(
            f"{job.import_type.value.title()} import '{job.filename}' finished: "
            f"{successful} added, {duplicate} duplicates, {failed} failed."
        ),
        priority=(
            NotificationPriority.LOW
            if job.status == ImportStatus.COMPLETED
            else NotificationPriority.MEDIUM
        ),
        resource_type="ImportJob",
        resource_id=job.id,
        dedupe_key=f"import-completed:{job.id}",
    )

    log_action(
        db,
        request,
        "Import Completed",
        company_id=company_id,
        user_id=user_id,
        entity_name=job.filename,
        resource_type="ImportJob",
        resource_id=job.id,
        details=(
            f"{successful} succeeded, {failed} failed, "
            f"{duplicate} duplicates."
        ),
    )

    db.commit()
    db.refresh(job)

    return ImportResultOut(
        id=job.id,
        status=job.status,
        total_records=job.total_records,
        successful_records=job.successful_records,
        failed_records=job.failed_records,
        duplicate_records=job.duplicate_records,
        completed_at=job.completed_at,
    )

@router.get("/history", response_model=ImportJobListResponse)
def import_history(
    import_type: Optional[ImportType] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    query = db.query(ImportJob).options(joinedload(ImportJob.uploader)).filter(
        ImportJob.company_id == company_id
    )
    if import_type:
        query = query.filter(ImportJob.import_type == import_type)

    total = query.count()
    jobs = query.order_by(ImportJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return ImportJobListResponse(items=[_job_to_out(j) for j in jobs], total=total)


@router.get("/{import_id}", response_model=ImportJobDetailOut)
def get_import(
    import_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    job = _get_job_or_404(db, company_id, import_id)
    return ImportJobDetailOut(
        **_job_to_out(job).model_dump(),
        valid_records=job.valid_records,
        invalid_records=job.invalid_records,
    )

@router.get(
    "/{import_id}/progress",
    response_model=ImportProgressOut,
)
def get_import_progress(
    import_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    job = _get_job_or_404(db, company_id, import_id)

    duration_seconds = None

    if job.started_at:
        end_time = job.completed_at or datetime.utcnow()
        duration_seconds = max(
            0,
            (end_time - job.started_at).total_seconds(),
        )

    return ImportProgressOut(
        id=job.id,
        status=job.status,
        total_records=job.total_records,
        processed_records=job.processed_records,
        successful_records=job.successful_records,
        failed_records=job.failed_records,
        duplicate_records=job.duplicate_records,
        skipped_records=job.skipped_records,
        progress_percentage=job.progress_percentage,
        processing_stage=job.processing_stage,
        cancellation_requested=job.cancellation_requested,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=duration_seconds,
    )

@router.post(
    "/{import_id}/cancel",
    response_model=ImportCancelResponse,
)
def cancel_import(
    import_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    job = _get_job_or_404(db, company_id, import_id)

    if job.status != ImportStatus.PROCESSING:
        raise HTTPException(
            status_code=400,
            detail="Only processing imports can be cancelled.",
        )

    if job.cancellation_requested:
        return ImportCancelResponse(
            id=job.id,
            status=job.status,
            cancellation_requested=True,
            message="Cancellation has already been requested.",
        )

    job.cancellation_requested = True
    job.processing_stage = "CANCELLATION_REQUESTED"

    db.commit()
    db.refresh(job)

    return ImportCancelResponse(
        id=job.id,
        status=job.status,
        cancellation_requested=True,
        message="Cancellation requested. The import will stop after the current row.",
    )

@router.get("/{import_id}/errors")
def get_import_errors(
    import_id: str,
    format: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    job = _get_job_or_404(db, company_id, import_id)
    rows = db.query(ImportErrorRow).filter(ImportErrorRow.import_job_id == job.id).order_by(
        ImportErrorRow.row_number.asc()
    ).all()

    if format == "json":
        return [
            ImportErrorOut(
                row_number=r.row_number, status=r.row_status,
                message=r.error_message, data=json.loads(r.row_data),
            )
            for r in rows
        ]

    # CSV download: original columns + Row Number / Issue Type / Error Reason appended.
    buffer = io.StringIO()
    fieldnames: list[str] = []
    parsed_rows = []
    for r in rows:
        data = json.loads(r.row_data)
        parsed_rows.append((r, data))
        for k in data.keys():
            if k not in fieldnames:
                fieldnames.append(k)
    fieldnames += ["Row Number", "Issue Type", "Error Reason"]

    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for r, data in parsed_rows:
        out_row = dict(data)
        out_row["Row Number"] = r.row_number
        out_row["Issue Type"] = r.row_status.value
        out_row["Error Reason"] = r.error_message
        writer.writerow(out_row)

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{job.filename}_errors.csv"'},
    )
