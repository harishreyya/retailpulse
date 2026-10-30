import enum
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SAEnum, Text, Boolean, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import gen_uuid


class ReportType(str, enum.Enum):
    SALES = "SALES"
    INVENTORY = "INVENTORY"
    CUSTOMER = "CUSTOMER"
    PRODUCT_PERFORMANCE = "PRODUCT_PERFORMANCE"
    STOCK_MOVEMENT = "STOCK_MOVEMENT"


class ReportFormat(str, enum.Enum):
    CSV = "CSV"
    PDF = "PDF"
    # On-screen only, no export produced yet. Used for Report History rows
    # created by the "view in table" flow before the user chooses to export.
    NONE = "NONE"


class ReportStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ScheduleFrequency(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class Report(Base):
    """
    One row per report *generation* — this is both "Report History" and
    the record that export/view endpoints hang off of. `filters_json`
    stores exactly what the user picked so the report (and its exported
    file) can always show "here's what this covers" even after the
    underlying data has moved on.
    """
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    generated_by = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    schedule_id = Column(UUID(as_uuid=False), ForeignKey("report_schedules.id", ondelete="SET NULL"), nullable=True, index=True)

    report_type = Column(SAEnum(ReportType), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    filters_json = Column(Text, nullable=False, default="{}")
    format = Column(SAEnum(ReportFormat), nullable=False, default=ReportFormat.NONE)
    status = Column(SAEnum(ReportStatus), nullable=False, default=ReportStatus.PENDING, index=True)
    error_message = Column(String(1000), nullable=True)

    row_count = Column(Integer, nullable=True)
    # The generated export file's bytes, stored directly in the DB row —
    # this project has no object storage (S3 etc.) configured, and report
    # files are small/text-based (CSV) or bounded (capped-row PDF), so a
    # bytea column is a reasonable, dependency-free choice here. See
    # services/reports.py for the row cap that keeps this from growing
    # unbounded.
    file_data = Column(Text, nullable=True)  # base64-encoded file bytes

    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)

    generator = relationship("User")
    schedule = relationship("ReportSchedule", back_populates="runs")

    __table_args__ = (
        Index("ix_reports_company_created", "company_id", "created_at"),
    )


class ReportSchedule(Base):
    __tablename__ = "report_schedules"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(255), nullable=False)
    report_type = Column(SAEnum(ReportType), nullable=False)
    filters_json = Column(Text, nullable=False, default="{}")
    format = Column(SAEnum(ReportFormat), nullable=False, default=ReportFormat.CSV)

    frequency = Column(SAEnum(ScheduleFrequency), nullable=False)
    # Minutes since midnight UTC the schedule should fire at (e.g. 6:30am -> 390).
    # Simpler and unambiguous to store/compare than a bare TIME column
    # combined with "which day" logic for weekly/monthly schedules.
    execution_minute_utc = Column(Integer, nullable=False, default=0)
    # For WEEKLY: 0=Monday..6=Sunday. For MONTHLY: 1-28 (day of month,
    # capped at 28 so it's valid in every month). Unused for DAILY.
    day_of_week = Column(Integer, nullable=True)
    day_of_month = Column(Integer, nullable=True)

    recipients_json = Column(Text, nullable=False, default="[]")  # list[str] emails
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(SAEnum(ReportStatus), nullable=True)
    next_run_at = Column(DateTime, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    creator = relationship("User")
    runs = relationship("Report", back_populates="schedule")
