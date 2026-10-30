from datetime import datetime
from decimal import Decimal
from typing import List

from pydantic import BaseModel


class AnalyticsKPIs(BaseModel):
    total_revenue: Decimal
    total_orders: int
    total_products_sold: int
    average_order_value: Decimal
    total_discount: Decimal
    total_tax: Decimal
    total_inventory_value: Decimal
    low_stock_products: int
    out_of_stock_products: int
    total_categories: int


class RevenueTrendPoint(BaseModel):
    period: str
    revenue: Decimal
    orders: int


class TopProductRow(BaseModel):
    product_id: str
    product_name: str
    sku: str
    quantity_sold: int
    revenue: Decimal


class TopCategoryRow(BaseModel):
    category_id: str
    category_name: str
    revenue: Decimal
    quantity_sold: int


class PaymentMethodBreakdown(BaseModel):
    payment_method: str
    revenue: Decimal
    orders: int


class SalesChannelBreakdown(BaseModel):
    sales_channel: str
    revenue: Decimal
    orders: int


class InventoryCategoryBreakdown(BaseModel):
    category_id: str
    category_name: str
    quantity: int
    value: Decimal


class InventoryStatusBreakdown(BaseModel):
    status: str
    count: int


class LowStockRow(BaseModel):
    product_id: str
    product_name: str
    sku: str
    available_stock: int
    reorder_level: int


class OutOfStockRow(BaseModel):
    product_id: str
    product_name: str
    sku: str
    updated_at: datetime


class CustomerRevenueRow(BaseModel):
    customer_id: str | None
    customer_name: str
    orders: int
    total_spend: Decimal
    average_order_value: Decimal


class AnalyticsSummary(BaseModel):
    kpis: AnalyticsKPIs
    revenue_trend: List[RevenueTrendPoint]
    top_products: List[TopProductRow]
    top_categories: List[TopCategoryRow]
    by_payment_method: List[PaymentMethodBreakdown]
    by_sales_channel: List[SalesChannelBreakdown]
    customer_revenue: List[CustomerRevenueRow]
    inventory_by_category: List[InventoryCategoryBreakdown]
    inventory_status_summary: List[InventoryStatusBreakdown]
    top_low_stock: List[LowStockRow]
    out_of_stock: List[OutOfStockRow]
    inventory_value_by_category: List[InventoryCategoryBreakdown]


class AnalyticsAuditEvent(BaseModel):
    action: str  # "Dashboard Viewed" | "Dashboard Filters Applied"
    details: str | None = None
