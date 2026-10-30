import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Enum as SAEnum,
    Integer, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import gen_uuid


class StockStatus(str, enum.Enum):
    IN_STOCK = "IN_STOCK"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"


# What the caller asks for on the /adjust endpoint.
class AdjustmentType(str, enum.Enum):
    STOCK_IN = "STOCK_IN"
    STOCK_OUT = "STOCK_OUT"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"


# Only meaningful when adjustment_type == MANUAL_ADJUSTMENT, since Stock In
# is always an increase and Stock Out is always a decrease.
class AdjustmentDirection(str, enum.Enum):
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"


# What actually gets recorded on the movement ledger.
class MovementType(str, enum.Enum):
    SALE = "SALE"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    STOCK_ADDITION = "STOCK_ADDITION"
    STOCK_REMOVAL = "STOCK_REMOVAL"


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    current_stock = Column(Integer, nullable=False, default=0)
    reserved_stock = Column(Integer, nullable=False, default=0)
    available_stock = Column(Integer, nullable=False, default=0)
    reorder_level = Column(Integer, nullable=False, default=10)
    stock_status = Column(SAEnum(StockStatus), nullable=False, default=StockStatus.OUT_OF_STOCK)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    product = relationship("Product")
    movements = relationship(
        "InventoryMovement", back_populates="inventory",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("company_id", "product_id", name="uq_inventory_company_product"),
    )

    def update_status(self) -> None:
        """
        Recompute available_stock and stock_status from current_stock,
        reserved_stock, and reorder_level. Call this any time one of those
        three inputs changes (product creation, sale processing, manual
        adjustment, reorder-level edit) so the two never drift apart.
        """
        self.available_stock = max(0, self.current_stock - self.reserved_stock)
        if self.available_stock <= 0:
            self.stock_status = StockStatus.OUT_OF_STOCK
        elif self.available_stock <= self.reorder_level:
            self.stock_status = StockStatus.LOW_STOCK
        else:
            self.stock_status = StockStatus.IN_STOCK


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    inventory_id = Column(UUID(as_uuid=False), ForeignKey("inventory.id", ondelete="CASCADE"), nullable=False, index=True)
    movement_type = Column(SAEnum(MovementType), nullable=False)
    quantity_changed = Column(Integer, nullable=False)  # signed: +in, -out
    previous_quantity = Column(Integer, nullable=False)
    updated_quantity = Column(Integer, nullable=False)
    reason = Column(String(255), nullable=False)
    remarks = Column(String(1000), nullable=True)
    performed_by = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    inventory = relationship("Inventory", back_populates="movements")
    performer = relationship("User")
