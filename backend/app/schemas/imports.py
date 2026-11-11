
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models import ImportType, ImportStatus, ImportRowStatus


# ---------- Shared row-level shapes ----------

class ImportPreviewRow(BaseModel):
    row_number: int
    data: dict


class ImportRowIssue(BaseModel):
    row_number: int
    status: ImportRowStatus
    message: str
    data: dict


class ImportValidationSummary(BaseModel):
    total_records: int
    valid_records: int
    invalid_records: int
    duplicate_records: int


# ---------- Upload / (re)validate response ----------

class ImportUploadResponse(BaseModel):
    import_id: str
    import_type: ImportType
    filename: str
    status: ImportStatus
    detected_columns: list[str]
    missing_columns: list[str]
    preview_rows: list[ImportPreviewRow]
    summary: ImportValidationSummary
    row_issues: list[ImportRowIssue]


# ---------- Import history ----------

class ImportJobOut(BaseModel):
    id: str
    import_type: ImportType
    filename: str
    uploaded_by_name: Optional[str] = None

    total_records: int
    successful_records: int
    failed_records: int
    duplicate_records: int
    skipped_records: int = 0
    processed_records: int = 0
    progress_percentage: int = 0
    processing_stage: Optional[str] = None

    status: ImportStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    cancellation_requested: bool = False


class ImportJobListResponse(BaseModel):
    items: list[ImportJobOut]
    total: int


class ImportJobDetailOut(ImportJobOut):
    valid_records: int
    invalid_records: int


# ---------- Process result ----------

class ImportResultOut(BaseModel):
    id: str
    status: ImportStatus
    total_records: int
    successful_records: int
    failed_records: int
    duplicate_records: int
    skipped_records: int = 0
    processed_records: int = 0
    progress_percentage: int = 0
    processing_stage: Optional[str] = None
    completed_at: Optional[datetime] = None


# ---------- Progress response ----------

class ImportProgressOut(BaseModel):
    id: str
    status: ImportStatus

    total_records: int
    processed_records: int
    successful_records: int
    failed_records: int
    duplicate_records: int
    skipped_records: int

    progress_percentage: int
    processing_stage: Optional[str] = None
    cancellation_requested: bool = False

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


# ---------- Cancellation response ----------

class ImportCancelResponse(BaseModel):
    id: str
    status: ImportStatus
    cancellation_requested: bool
    message: str


# ---------- Error report ----------

class ImportErrorOut(BaseModel):
    row_number: int
    status: ImportRowStatus
    message: str
    data: dict
