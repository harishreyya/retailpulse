
import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, ForeignKey,
    Enum as SAEnum, Integer, Text, Boolean,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import gen_uuid


class ImportType(str, enum.Enum):
    PRODUCTS = "PRODUCTS"
    INVENTORY = "INVENTORY"
    CUSTOMERS = "CUSTOMERS"
    SALES = "SALES"


class ImportStatus(str, enum.Enum):
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ImportRowStatus(str, enum.Enum):
    INVALID = "INVALID"
    DUPLICATE = "DUPLICATE"
    FAILED = "FAILED"


class ImportJob(Base):
    """
    One row per uploaded CSV.

    The raw CSV is staged between upload, validation and processing.
    Processing progress is persisted so the frontend can poll job status.
    """

    __tablename__ = "import_jobs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(
        UUID(as_uuid=False),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    import_type = Column(SAEnum(ImportType), nullable=False)
    filename = Column(String(255), nullable=False)
    uploaded_by = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_content = Column(Text, nullable=False)

    total_records = Column(Integer, nullable=False, default=0)
    valid_records = Column(Integer, nullable=False, default=0)
    invalid_records = Column(Integer, nullable=False, default=0)
    duplicate_records = Column(Integer, nullable=False, default=0)
    successful_records = Column(Integer, nullable=False, default=0)
    failed_records = Column(Integer, nullable=False, default=0)

    # Background processing progress
    processed_records = Column(Integer, nullable=False, default=0)
    skipped_records = Column(Integer, nullable=False, default=0)
    progress_percentage = Column(Integer, nullable=False, default=0)
    processing_stage = Column(String(50), nullable=True)
    cancellation_requested = Column(Boolean, nullable=False, default=False)

    status = Column(
        SAEnum(ImportStatus),
        nullable=False,
        default=ImportStatus.PENDING,
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    uploader = relationship("User")
    row_errors = relationship(
        "ImportError",
        back_populates="job",
        cascade="all, delete-orphan",
    )

    __table_args__ = ()


class ImportError(Base):
    """Detailed per-row problem, populated by validation and processing."""

    __tablename__ = "import_errors"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    import_job_id = Column(
        UUID(as_uuid=False),
        ForeignKey("import_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    row_number = Column(Integer, nullable=False)
    row_status = Column(SAEnum(ImportRowStatus), nullable=False)
    row_data = Column(Text, nullable=False)
    error_message = Column(String(1000), nullable=False)

    job = relationship("ImportJob", back_populates="row_errors")
