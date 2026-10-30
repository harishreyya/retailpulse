from datetime import date, datetime
from decimal import Decimal
from typing import Optional
import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import CustomerType, CustomerStatus, CustomerGender, CustomerSegment, CustomerActivityType

PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\s\-().]{6,19}$")


def _validate_phone(value: str) -> str:
    if not PHONE_PATTERN.match(value.strip()):
        raise ValueError("Enter a valid phone number (7-20 digits, may include +, spaces, - or parentheses)")
    return value.strip()


# ---------- Customer CRUD ----------

class CustomerCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=150)
    last_name: str = Field(..., min_length=1, max_length=150)
    email: EmailStr
    phone: str = Field(..., min_length=1, max_length=50)
    date_of_birth: Optional[date] = None
    gender: Optional[CustomerGender] = None
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=120)
    state: Optional[str] = Field(None, max_length=120)
    country: Optional[str] = Field(None, max_length=120)
    postal_code: Optional[str] = Field(None, max_length=30)
    customer_type: CustomerType = CustomerType.RETAIL
    preferred_channel: Optional[str] = None
    status: CustomerStatus = CustomerStatus.ACTIVE

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_phone(v)


class CustomerUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=150)
    last_name: Optional[str] = Field(None, min_length=1, max_length=150)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, min_length=1, max_length=50)
    date_of_birth: Optional[date] = None
    gender: Optional[CustomerGender] = None
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=120)
    state: Optional[str] = Field(None, max_length=120)
    country: Optional[str] = Field(None, max_length=120)
    postal_code: Optional[str] = Field(None, max_length=30)
    customer_type: Optional[CustomerType] = None
    preferred_channel: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        return _validate_phone(v) if v is not None else v


class CustomerStatusUpdate(BaseModel):
    status: CustomerStatus


# ---------- Nested refs ----------

class CustomerProductRef(BaseModel):
    id: str
    name: str
    sku: str

    class Config:
        from_attributes = True


class CustomerCategoryRef(BaseModel):
    id: str
    name: str

    class Config:
        from_attributes = True


class CustomerPurchaseSummaryOut(BaseModel):
    total_orders: int
    total_revenue: Decimal
    total_quantity: int
    average_order_value: Decimal
    first_purchase_date: Optional[datetime] = None
    last_purchase_date: Optional[datetime] = None
    favorite_product: Optional[CustomerProductRef] = None
    favorite_category: Optional[CustomerCategoryRef] = None

    class Config:
        from_attributes = True


EMPTY_SUMMARY = CustomerPurchaseSummaryOut(
    total_orders=0, total_revenue=Decimal("0"), total_quantity=0, average_order_value=Decimal("0"),
)


# ---------- Output ----------

class CustomerOut(BaseModel):
    id: str
    customer_code: str
    first_name: str
    last_name: str
    full_name: str
    email: str
    phone: str
    date_of_birth: Optional[date] = None
    gender: Optional[CustomerGender] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    customer_type: CustomerType
    preferred_channel: Optional[str] = None
    status: CustomerStatus
    segment: CustomerSegment
    purchase_summary: Optional[CustomerPurchaseSummaryOut] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CustomerListItem(BaseModel):
    id: str
    customer_code: str
    full_name: str
    email: str
    phone: str
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    customer_type: CustomerType
    status: CustomerStatus
    segment: CustomerSegment
    total_orders: int
    total_revenue: Decimal
    last_purchase_date: Optional[datetime] = None
    created_at: datetime


class CustomerListResponse(BaseModel):
    items: list[CustomerListItem]
    total: int


class CustomerActivityOut(BaseModel):
    id: str
    activity_type: CustomerActivityType
    description: str
    created_at: datetime

    class Config:
        from_attributes = True


class CustomerRecentSale(BaseModel):
    id: str
    invoice_number: str
    sale_date: datetime
    total_amount: Decimal
    item_count: int


class CustomerProfileOut(BaseModel):
    customer: CustomerOut
    recent_activities: list[CustomerActivityOut]
    recent_transactions: list[CustomerRecentSale]


# ---------- Analytics ----------

class CustomerAnalyticsKPIs(BaseModel):
    total_customers: int
    active_customers: int
    new_customers: int          # registered within the selected/default window
    returning_customers: int    # customers with 2+ orders
    average_customer_spend: Decimal
    total_revenue_generated: Decimal
    average_purchase_frequency: Decimal   # avg orders per customer with at least 1 order


class CustomerGrowthPoint(BaseModel):
    period: str
    new_customers: int
    total_customers: int


class NewVsReturningPoint(BaseModel):
    period: str
    new_customers: int
    returning_customers: int


class RevenueByTypeRow(BaseModel):
    customer_type: CustomerType
    revenue: Decimal
    customer_count: int


class TopCustomerRow(BaseModel):
    customer_id: str
    customer_code: str
    full_name: str
    revenue: Decimal
    total_orders: int


class PurchaseFrequencyBucket(BaseModel):
    bucket: str
    customer_count: int


class LocationRow(BaseModel):
    location: str
    customer_count: int


class MonthlyAcquisitionPoint(BaseModel):
    period: str
    new_customers: int


class SpendingDistributionBucket(BaseModel):
    bucket: str
    customer_count: int


class SegmentBreakdown(BaseModel):
    segment: CustomerSegment
    customer_count: int


class CustomerAnalyticsSummary(BaseModel):
    kpis: CustomerAnalyticsKPIs
    growth_trend: list[CustomerGrowthPoint]
    new_vs_returning: list[NewVsReturningPoint]
    revenue_by_type: list[RevenueByTypeRow]
    top_customers: list[TopCustomerRow]
    purchase_frequency: list[PurchaseFrequencyBucket]
    location_distribution: list[LocationRow]
    monthly_acquisition: list[MonthlyAcquisitionPoint]
    spending_distribution: list[SpendingDistributionBucket]
    segment_breakdown: list[SegmentBreakdown]
