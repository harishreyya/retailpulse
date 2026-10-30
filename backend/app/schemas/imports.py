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
# Both POST /import/upload and POST /import/{id}/validate return this shape:
# upload does the first parse + validate, /validate re-runs validation
# against current DB state (e.g. if new SKUs were added since upload).

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
    status: ImportStatus
    created_at: datetime
    completed_at: Optional[datetime] = None


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
    completed_at: Optional[datetime] = None


class ImportErrorOut(BaseModel):
    row_number: int
    status: ImportRowStatus
    message: str
    data: dict
