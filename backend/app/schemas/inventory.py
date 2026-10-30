from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models import (
    StockStatus, AdjustmentType, AdjustmentDirection, MovementType,
)


# ---------- Inventory ----------

class InventoryProductOut(BaseModel):
    id: str
    name: str
    sku: str
    brand: Optional[str] = None
    unit_of_measure: str
    category_id: str
    category_name: str


class InventoryOut(BaseModel):
    id: str
    product: InventoryProductOut
    current_stock: int
    reserved_stock: int
    available_stock: int
    reorder_level: int
    stock_status: StockStatus
    updated_at: datetime


class InventoryListResponse(BaseModel):
    items: List[InventoryOut]
    total: int


class ReorderLevelUpdate(BaseModel):
    reorder_level: int = Field(..., ge=0)


# ---------- Stock Adjustments / Movements ----------

class StockAdjustmentCreate(BaseModel):
    adjustment_type: AdjustmentType
    direction: Optional[AdjustmentDirection] = None
    quantity: int = Field(..., gt=0)
    reason: str = Field(..., min_length=1, max_length=255)
    remarks: Optional[str] = Field(None, max_length=1000)

    @model_validator(mode="after")
    def direction_required_for_manual(self):
        if self.adjustment_type == AdjustmentType.MANUAL_ADJUSTMENT and self.direction is None:
            raise ValueError("Direction (INCREASE or DECREASE) is required for a manual adjustment")
        return self


class MovementPerformerOut(BaseModel):
    id: str
    name: str


class MovementOut(BaseModel):
    id: str
    movement_type: MovementType
    quantity_changed: int
    previous_quantity: int
    updated_quantity: int
    reason: str
    remarks: Optional[str] = None
    performed_by: Optional[MovementPerformerOut] = None
    created_at: datetime


class MovementListResponse(BaseModel):
    items: List[MovementOut]
    total: int


# ---------- Dashboard ----------

class CategoryBreakdown(BaseModel):
    category: str
    quantity: int


class StatusBreakdown(BaseModel):
    status: StockStatus
    count: int


class InventoryDashboardSummary(BaseModel):
    total_products: int
    total_quantity: int
    low_stock_count: int
    out_of_stock_count: int
    by_category: List[CategoryBreakdown]
    by_status: List[StatusBreakdown]
