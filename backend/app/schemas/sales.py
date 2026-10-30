from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.models import SalesChannel, PaymentMethod, PaymentStatus
from app.schemas.catalog import ProductCategoryOut


# ---------- Sale Items ----------

class SaleItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)  # defaults to product's current price if omitted
    discount: Decimal = Field(0, ge=0)
    tax: Decimal = Field(0, ge=0)

    @model_validator(mode="after")
    def discount_within_line_value(self):
        if self.unit_price is not None:
            line_value = self.quantity * self.unit_price
            if self.discount > line_value:
                raise ValueError("Discount cannot exceed total product value")
        return self


class SaleItemProductRef(BaseModel):
    id: str
    name: str
    sku: str

    class Config:
        from_attributes = True


class SaleItemOut(BaseModel):
    id: str
    product: SaleItemProductRef
    category: ProductCategoryOut
    quantity: int
    unit_price: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal

    class Config:
        from_attributes = True


# ---------- Sale ----------

class SaleCreate(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=255)
    # Task 6: optional link to a Customer record. When provided, purchase
    # history/segmentation for that customer is recalculated automatically.
    customer_id: Optional[str] = None
    sale_date: Optional[datetime] = None
    sales_channel: SalesChannel
    payment_method: PaymentMethod
    payment_status: PaymentStatus = PaymentStatus.PAID
    notes: Optional[str] = Field(None, max_length=1000)
    items: list[SaleItemCreate] = Field(..., min_length=1)


class SaleUpdate(BaseModel):
    customer_name: Optional[str] = Field(None, min_length=1, max_length=255)
    customer_id: Optional[str] = None
    clear_customer: bool = False  # explicit flag to unlink, since customer_id=None means "leave unchanged"
    sale_date: Optional[datetime] = None
    sales_channel: Optional[SalesChannel] = None
    payment_method: Optional[PaymentMethod] = None
    payment_status: Optional[PaymentStatus] = None
    notes: Optional[str] = Field(None, max_length=1000)
    items: Optional[list[SaleItemCreate]] = Field(None, min_length=1)


class SaleCreatorRef(BaseModel):
    id: str
    name: str

    class Config:
        from_attributes = True


class SaleOut(BaseModel):
    id: str
    invoice_number: str
    customer_name: str
    customer_id: Optional[str] = None
    sale_date: datetime
    sales_channel: SalesChannel
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    notes: Optional[str] = None
    total_amount: Decimal
    items: list[SaleItemOut]
    creator: Optional[SaleCreatorRef] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SaleListItem(BaseModel):
    id: str
    invoice_number: str
    customer_name: str
    customer_id: Optional[str] = None
    sale_date: datetime
    sales_channel: SalesChannel
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    total_amount: Decimal
    item_count: int

    class Config:
        from_attributes = True


class SaleListResponse(BaseModel):
    items: list[SaleListItem]
    total: int


class SalesDashboardSummary(BaseModel):
    total_sales: int          # total units sold across all sale items
    total_revenue: Decimal    # sum of total_amount across all sales
    total_orders: int         # number of invoices
    average_order_value: Decimal
