from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, EmailStr

from app.models import ReportType, ReportFormat, ReportStatus, ScheduleFrequency


# ---------- Shared filter shape ----------
# Every field is optional; which ones a given report_type actually uses is
# documented per-type in services/reports.py. Sent as-is by the frontend
# and stored as JSON on the Report/ReportSchedule row.

class ReportFilters(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    product_id: Optional[str] = None
    category_id: Optional[str] = None
    brand: Optional[str] = None
    customer_id: Optional[str] = None
    sales_status: Optional[str] = None   # PaymentStatus value
    stock_status: Optional[str] = None   # StockStatus value
    movement_type: Optional[str] = None  # MovementType value
    search: Optional[str] = None


# ---------- Generation ----------

class ReportGenerateRequest(BaseModel):
    report_type: ReportType
    filters: ReportFilters = ReportFilters()
    sort_by: Optional[str] = None
    sort_dir: str = Field("desc", pattern="^(asc|desc)$")
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


class ReportColumn(BaseModel):
    key: str
    label: str


class ReportGenerateResponse(BaseModel):
    report_id: str
    report_type: ReportType
    name: str
    columns: list[ReportColumn]
    rows: list[dict]
    total: int
    page: int
    page_size: int
    filters: ReportFilters
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    generated_at: datetime


# ---------- History ----------

class ReportHistoryRow(BaseModel):
    id: str
    report_type: ReportType
    name: str
    generated_by_name: Optional[str] = None
    filters: ReportFilters
    format: ReportFormat
    status: ReportStatus
    error_message: Optional[str] = None
    row_count: Optional[int] = None
    schedule_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class ReportHistoryListResponse(BaseModel):
    items: list[ReportHistoryRow]
    total: int
    page: int
    page_size: int


class ReportFilterOptions(BaseModel):
    categories: list[dict]
    brands: list[str]
    customers: list[dict]


# ---------- Schedules ----------

class ReportScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    report_type: ReportType
    filters: ReportFilters = ReportFilters()
    format: ReportFormat = ReportFormat.CSV
    frequency: ScheduleFrequency
    execution_time: str = Field(..., pattern="^([01]\\d|2[0-3]):[0-5]\\d$")  # "HH:MM", UTC
    day_of_week: Optional[int] = Field(None, ge=0, le=6)   # required for WEEKLY
    day_of_month: Optional[int] = Field(None, ge=1, le=28)  # required for MONTHLY
    recipients: list[EmailStr] = Field(default_factory=list)
    is_active: bool = True


class ReportScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    filters: Optional[ReportFilters] = None
    format: Optional[ReportFormat] = None
    frequency: Optional[ScheduleFrequency] = None
    execution_time: Optional[str] = Field(None, pattern="^([01]\\d|2[0-3]):[0-5]\\d$")
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    day_of_month: Optional[int] = Field(None, ge=1, le=28)
    recipients: Optional[list[EmailStr]] = None
    is_active: Optional[bool] = None


class ReportScheduleOut(BaseModel):
    id: str
    name: str
    report_type: ReportType
    filters: ReportFilters
    format: ReportFormat
    frequency: ScheduleFrequency
    execution_time: str
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    recipients: list[str]
    is_active: bool
    created_by_name: Optional[str] = None
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[ReportStatus] = None
    next_run_at: Optional[datetime] = None
    created_at: datetime


class ReportScheduleListResponse(BaseModel):
    items: list[ReportScheduleOut]
    total: int
