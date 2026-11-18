
import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    Text,
    Boolean,
    JSON,
    Index,
    UniqueConstraint,
)

from sqlalchemy.dialects.postgresql import UUID

from app.database import Base
from app.models.base import gen_uuid


class WorkflowRequestType(str, enum.Enum):
    STOCK_ADJUSTMENT = "STOCK_ADJUSTMENT"
    PRODUCT_DEACTIVATION = "PRODUCT_DEACTIVATION"
    PRODUCT_PRICE_CHANGE = "PRODUCT_PRICE_CHANGE"
    CUSTOMER_INFORMATION_CHANGE = "CUSTOMER_INFORMATION_CHANGE"
    INVENTORY_IMPORT = "INVENTORY_IMPORT"


class WorkflowRequestStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class WorkflowApprovalHistory(Base):
    __tablename__ = "workflow_approval_history"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)

    request_id = Column(
        UUID(as_uuid=False),
        ForeignKey("workflow_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    company_id = Column(
        UUID(as_uuid=False),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    actor_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    action = Column(String(50), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    comments = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


class WorkflowRequest(Base):
    __tablename__ = "workflow_requests"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)

    company_id = Column(
        UUID(as_uuid=False),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    request_type = Column(
        SAEnum(WorkflowRequestType, name="workflowrequesttype"),
        nullable=False,
        index=True,
    )

    status = Column(
        SAEnum(WorkflowRequestStatus, name="workflowrequeststatus"),
        nullable=False,
        default=WorkflowRequestStatus.DRAFT,
        index=True,
    )

    requester_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    approver_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    approver_role = Column(String(30), nullable=True)

    related_record_type = Column(String(50), nullable=True)
    related_record_id = Column(UUID(as_uuid=False), nullable=True)

    requested_changes = Column(JSON, nullable=False)
    before_values = Column(JSON, nullable=True)

    reason = Column(Text, nullable=False)

    rejection_reason = Column(Text, nullable=True)

    submitted_at = Column(DateTime, nullable=True)
    decided_at = Column(DateTime, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_workflow_company_status_created",
            "company_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_workflow_company_requester",
            "company_id",
            "requester_id",
        ),
        Index(
            "ix_workflow_related_record",
            "related_record_type",
            "related_record_id",
        ),
    )


class WorkflowConfig(Base):
    __tablename__ = "workflow_configs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)

    company_id = Column(
        UUID(as_uuid=False),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    request_type = Column(
        SAEnum(
            WorkflowRequestType,
            name="workflowrequesttype",
            create_type=False,
        ),
        nullable=False,
    )

    approver_role = Column(
        String(30),
        nullable=False,
        default="COMPANY_ADMIN",
    )

    approval_required = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    allow_self_approval = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "request_type",
            name="uq_workflow_config_company_type",
        ),
    )
