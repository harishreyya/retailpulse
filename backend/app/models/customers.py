import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, Date, ForeignKey, Enum as SAEnum,
    Numeric, Integer, UniqueConstraint, Boolean, Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import gen_uuid


class CustomerType(str, enum.Enum):
    RETAIL = "RETAIL"
    WHOLESALE = "WHOLESALE"
    CORPORATE = "CORPORATE"


class CustomerStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class CustomerGender(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"
    UNSPECIFIED = "UNSPECIFIED"


class CustomerSegment(str, enum.Enum):
    NEW = "NEW"
    REGULAR = "REGULAR"
    LOYAL = "LOYAL"
    VIP = "VIP"


class CustomerActivityType(str, enum.Enum):
    REGISTERED = "REGISTERED"
    PROFILE_UPDATED = "PROFILE_UPDATED"
    FIRST_PURCHASE = "FIRST_PURCHASE"
    LARGE_PURCHASE = "LARGE_PURCHASE"
    DEACTIVATED = "DEACTIVATED"
    REACTIVATED = "REACTIVATED"
    SEGMENT_CHANGED = "SEGMENT_CHANGED"


class Customer(Base):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    # Human-friendly auto-generated identifier, e.g. CUST-000123 (unique per company).
    customer_code = Column(String(30), nullable=False, index=True)

    # Task 8: structured name fields. full_name stays as an auto-derived
    # "First Last" convenience column since Customer Analytics, Forecasting
    # notifications, and the Sales customer picker (Task 6/7) all display
    # full_name directly — keeping it avoids touching every consumer.
    first_name = Column(String(150), nullable=False, default="")
    last_name = Column(String(150), nullable=False, default="")
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(SAEnum(CustomerGender), nullable=True)

    address = Column(String(500), nullable=True)
    city = Column(String(120), nullable=True)
    state = Column(String(120), nullable=True)
    country = Column(String(120), nullable=True)
    postal_code = Column(String(30), nullable=True)

    customer_type = Column(SAEnum(CustomerType), nullable=False, default=CustomerType.RETAIL)
    # Reuses the same channel vocabulary as Sale.sales_channel (RETAIL_STORE / ONLINE_STORE / MARKETPLACE).
    preferred_channel = Column(String(30), nullable=True)
    status = Column(SAEnum(CustomerStatus), nullable=False, default=CustomerStatus.ACTIVE)
    segment = Column(SAEnum(CustomerSegment), nullable=False, default=CustomerSegment.NEW)

    created_by = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deactivated_at = Column(DateTime, nullable=True)
    # Task 8: soft delete. DELETE /customers/{id} now sets this instead of
    # removing the row; every list/get query filters it out below.
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)

    purchase_summary = relationship(
        "CustomerPurchaseSummary", back_populates="customer",
        uselist=False, cascade="all, delete-orphan",
    )
    activities = relationship(
        "CustomerActivity", back_populates="customer",
        cascade="all, delete-orphan", order_by="desc(CustomerActivity.created_at)",
    )
    creator = relationship("User")

    __table_args__ = (
        UniqueConstraint("company_id", "customer_code", name="uq_customers_company_code"),
        Index("uq_customers_company_email_live", "company_id", "email", unique=True,
              postgresql_where=(is_deleted.is_(False))),
        Index("uq_customers_company_phone_live", "company_id", "phone", unique=True,
              postgresql_where=(is_deleted.is_(False))),
    )


class CustomerPurchaseSummary(Base):
    """
    One row per customer, recalculated in full every time a sale linked to
    that customer is created, edited, or deleted (see app/services/customers.py).
    """
    __tablename__ = "customer_purchase_summary"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    total_orders = Column(Integer, nullable=False, default=0)
    total_revenue = Column(Numeric(14, 2), nullable=False, default=0)
    total_quantity = Column(Integer, nullable=False, default=0)
    average_order_value = Column(Numeric(14, 2), nullable=False, default=0)
    first_purchase_date = Column(DateTime, nullable=True)
    last_purchase_date = Column(DateTime, nullable=True)

    favorite_product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    favorite_category_id = Column(UUID(as_uuid=False), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    customer = relationship("Customer", back_populates="purchase_summary")
    favorite_product = relationship("Product")
    favorite_category = relationship("Category")


class CustomerActivity(Base):
    """Chronological timeline entries shown on the Customer Profile page."""
    __tablename__ = "customer_activities"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type = Column(SAEnum(CustomerActivityType), nullable=False)
    description = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    customer = relationship("Customer", back_populates="activities")
