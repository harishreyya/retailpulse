
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import gen_uuid


class DataQualityIssue(Base):
    """
    Stores one identified data-quality problem for a company.

    The fingerprint identifies the same underlying problem across
    reconciliation runs so we can prevent duplicate issues.
    """


    __tablename__ = "data_quality_issues"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=gen_uuid,
    )

    company_id = Column(
        UUID(as_uuid=False),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    fingerprint = Column(String(255), nullable=False)

    issue_type = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), nullable=False, default="WARNING", index=True)
    module = Column(String(50), nullable=False, index=True)

    record_type = Column(String(50), nullable=True)
    record_id = Column(String(64), nullable=True, index=True)
    record_label = Column(String(255), nullable=True)

    description = Column(Text, nullable=False)
    details_json = Column(Text, nullable=False, default="{}")

    status = Column(String(20), nullable=False, default="OPEN", index=True)

    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_detected_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    resolved_at = Column(DateTime, nullable=True)

    resolved_by = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    resolution_note = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    resolver = relationship("User", foreign_keys=[resolved_by])

    events = relationship(
        "DataQualityIssueEvent",
        back_populates="issue",
        cascade="all, delete-orphan",
        order_by="DataQualityIssueEvent.created_at",
    )

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "fingerprint",
            name="uq_data_quality_issue_fingerprint",
        ),
        Index(
            "ix_dq_company_status_detected",
            "company_id",
            "status",
            "detected_at",
        ),
    )


class ReconciliationRun(Base):
    """
    Records each manual or automatic reconciliation execution.
    """

    __tablename__ = "reconciliation_runs"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=gen_uuid,
    )

    company_id = Column(
        UUID(as_uuid=False),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    triggered_by = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    status = Column(String(30), nullable=False, default="RUNNING", index=True)

    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    records_checked = Column(Integer, nullable=False, default=0)
    issues_detected = Column(Integer, nullable=False, default=0)
    issues_resolved = Column(Integer, nullable=False, default=0)
    failed_checks = Column(Integer, nullable=False, default=0)

    summary_json = Column(Text, nullable=False, default="{}")
    error_message = Column(Text, nullable=True)

    trigger_user = relationship("User", foreign_keys=[triggered_by])

    __table_args__ = (
        Index(
            "ix_dq_runs_company_started",
            "company_id",
            "started_at",
        ),
    )


class DataQualityIssueEvent(Base):
    """
    Preserves the history of status changes and resolution actions.
    """

    __tablename__ = "data_quality_issue_events"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=gen_uuid,
    )

    company_id = Column(
        UUID(as_uuid=False),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    issue_id = Column(
        UUID(as_uuid=False),
        ForeignKey("data_quality_issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    previous_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    note = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    issue = relationship(
        "DataQualityIssue",
        back_populates="events",
    )

    user = relationship("User")
