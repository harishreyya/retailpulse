import enum
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SAEnum, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import gen_uuid


class NotificationType(str, enum.Enum):
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    STOCKOUT_RISK = "STOCKOUT_RISK"
    OVERSTOCK = "OVERSTOCK"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    CUSTOMER_REGISTERED = "CUSTOMER_REGISTERED"
    CUSTOMER_VIP = "CUSTOMER_VIP"
    CUSTOMER_INACTIVE = "CUSTOMER_INACTIVE"
    CUSTOMER_FIRST_PURCHASE = "CUSTOMER_FIRST_PURCHASE"
    SALES_ALERT = "SALES_ALERT"
    FORECAST_STOCK_RUNOUT = "FORECAST_STOCK_RUNOUT"
    FORECAST_DEMAND_EXCEEDS_STOCK = "FORECAST_DEMAND_EXCEEDS_STOCK"
    FORECAST_DEMAND_GROWTH = "FORECAST_DEMAND_GROWTH"
    IMPORT_COMPLETED = "IMPORT_COMPLETED"
    IMPORT_FAILED = "IMPORT_FAILED"
    SYSTEM_ALERT = "SYSTEM_ALERT"
    # Kept for backward compatibility with any existing rows written under
    # the old name before IMPORT_COMPLETED/IMPORT_FAILED were split out.
    DATA_IMPORT_COMPLETED = "DATA_IMPORT_COMPLETED"


class NotificationPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    # Every notification row belongs to exactly one recipient. Conditions
    # that should reach several users (e.g. "all Admins") are fanned out
    # into one row per eligible user at creation time — see
    # services/notifications.py's `notify_roles()`. This is what makes
    # "does notification X belong to the authenticated user" a trivial,
    # unambiguous check rather than a shared-row-with-per-user-read-state
    # problem.
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True)
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True)
    # Generic resource link, for things product_id/customer_id can't cover
    # (an import job, a sale, etc.) — mirrors the pattern already used in
    # AuditLog for the same reason.
    resource_type = Column(String(50), nullable=True, index=True)
    resource_id = Column(String(64), nullable=True, index=True)

    type = Column(SAEnum(NotificationType), nullable=False, index=True)
    priority = Column(SAEnum(NotificationPriority), nullable=False, default=NotificationPriority.LOW, index=True)
    title = Column(String(150), nullable=False)
    message = Column(String(500), nullable=False)

    # De-duplication key: while a condition remains open (e.g. a product
    # stays below its reorder point), re-evaluating it must not create a
    # fresh row every time. See services/notifications.py's
    # `upsert_condition_notification()`.
    dedupe_key = Column(String(150), nullable=True, index=True)

    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User")
    product = relationship("Product")
    customer = relationship("Customer")

    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        # One open (unread) notification per user per condition — enforced
        # in application code (see upsert_condition_notification), this
        # index just makes that lookup fast.
        Index("ix_notifications_dedupe", "user_id", "dedupe_key", "is_read"),
    )
