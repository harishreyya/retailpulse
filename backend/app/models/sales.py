import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Enum as SAEnum,
    Numeric, Integer, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import gen_uuid


class SalesChannel(str, enum.Enum):
    RETAIL_STORE = "RETAIL_STORE"
    ONLINE_STORE = "ONLINE_STORE"
    MARKETPLACE = "MARKETPLACE"


class PaymentMethod(str, enum.Enum):
    CASH = "CASH"
    CARD = "CARD"
    UPI = "UPI"
    BANK_TRANSFER = "BANK_TRANSFER"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    REFUNDED = "REFUNDED"


class Sale(Base):
    __tablename__ = "sales"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_number = Column(String(50), nullable=False, index=True)
    customer_name = Column(String(255), nullable=False)
    # Task 6: optional link to a Customer record. customer_name above is kept
    # as a point-in-time snapshot for display even when this is set/unset later.
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    sale_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    sales_channel = Column(SAEnum(SalesChannel), nullable=False)
    payment_method = Column(SAEnum(PaymentMethod), nullable=False)
    # Task 9: payment/order status, distinct from payment_method (how vs. whether paid).
    payment_status = Column(SAEnum(PaymentStatus), nullable=False, default=PaymentStatus.PAID)
    notes = Column(String(1000), nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    created_by = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    creator = relationship("User")

    __table_args__ = (
        UniqueConstraint("company_id", "invoice_number", name="uq_sales_company_invoice"),
    )


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    sale_id = Column(UUID(as_uuid=False), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    category_id = Column(UUID(as_uuid=False), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    discount = Column(Numeric(12, 2), nullable=False, default=0)
    tax = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False)

    sale = relationship("Sale", back_populates="items")
    product = relationship("Product")
    category = relationship("Category")
