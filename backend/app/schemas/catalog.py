from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.models import CategoryStatus, ProductStatus


# ---------- Category ----------

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    status: CategoryStatus = CategoryStatus.ACTIVE


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    status: Optional[CategoryStatus] = None


class CategoryOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: CategoryStatus
    product_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------- Product ----------

class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    sku: str = Field(..., min_length=1, max_length=100)
    category_id: str
    brand: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    unit_price: Decimal = Field(..., gt=0)
    cost_price: Decimal = Field(..., ge=0)
    stock_quantity: int = Field(0, ge=0)
    unit_of_measure: str = Field(..., min_length=1, max_length=50)
    status: ProductStatus = ProductStatus.ACTIVE

    @model_validator(mode="after")
    def cost_not_greater_than_price(self):
        if self.cost_price > self.unit_price:
            raise ValueError("Cost Price cannot exceed Unit Price")
        return self


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    sku: Optional[str] = Field(None, min_length=1, max_length=100)
    category_id: Optional[str] = None
    brand: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    unit_price: Optional[Decimal] = Field(None, gt=0)
    cost_price: Optional[Decimal] = Field(None, ge=0)
    stock_quantity: Optional[int] = Field(None, ge=0)
    unit_of_measure: Optional[str] = Field(None, min_length=1, max_length=50)
    status: Optional[ProductStatus] = None

    @model_validator(mode="after")
    def cost_not_greater_than_price(self):
        if self.cost_price is not None and self.unit_price is not None:
            if self.cost_price > self.unit_price:
                raise ValueError("Cost Price cannot exceed Unit Price")
        return self


class ProductCategoryOut(BaseModel):
    id: str
    name: str

    class Config:
        from_attributes = True


class ProductOut(BaseModel):
    id: str
    name: str
    sku: str
    brand: Optional[str] = None
    description: Optional[str] = None
    unit_price: Decimal
    cost_price: Decimal
    stock_quantity: int
    unit_of_measure: str
    status: ProductStatus
    category: ProductCategoryOut
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ProductOptionOut(BaseModel):
    """Lightweight product shape for the sales-entry product picker."""
    id: str
    name: str
    sku: str
    unit_price: Decimal
    stock_quantity: int
    unit_of_measure: str
    category: ProductCategoryOut

    class Config:
        from_attributes = True
        
class ProductListResponse(BaseModel):
    items: list[ProductOut]
    total: int


class DashboardSummary(BaseModel):
    total_products: int
    active_products: int
    inactive_products: int
    total_categories: int
