import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Enum as SAEnum, Numeric, Integer,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import gen_uuid


class ForecastPeriod(str, enum.Enum):
    NEXT_7_DAYS = "NEXT_7_DAYS"
    NEXT_30_DAYS = "NEXT_30_DAYS"
    NEXT_90_DAYS = "NEXT_90_DAYS"
    CUSTOM = "CUSTOM"


class RecommendationType(str, enum.Enum):
    """Task 7's original 4-tier recommendation, still used by the Demand
    Forecasting dashboard/notifications/export flow. Left untouched so that
    module keeps working exactly as before."""
    REORDER_SOON = "REORDER_SOON"
    OVERSTOCK_RISK = "OVERSTOCK_RISK"
    STOCK_HEALTHY = "STOCK_HEALTHY"
    IMMEDIATE_RESTOCK_REQUIRED = "IMMEDIATE_RESTOCK_REQUIRED"


class StockRisk(str, enum.Enum):
    """Task 11's 5-tier supply-chain risk classification. Separate from
    RecommendationType because it's driven by a different, more granular
    formula (reorder point / lead time / safety stock) and the Inventory
    Forecast dashboard needs the finer distinction between 'about to run
    out' (STOCKOUT_RISK) and 'already at zero' (OUT_OF_STOCK)."""
    OUT_OF_STOCK = "OUT_OF_STOCK"
    STOCKOUT_RISK = "STOCKOUT_RISK"
    LOW_STOCK = "LOW_STOCK"
    HEALTHY = "HEALTHY"
    OVERSTOCK = "OVERSTOCK"


class DemandForecast(Base):
    """
    A product-level row has both product_id and category_id set.
    A category-level (aggregate) row has product_id NULL and only
    category_id set. Re-generating a forecast for the same
    product/category + forecast_period updates this row in place
    (see app/services/forecasting.py) rather than creating a duplicate.

    Task 11 adds the supply-chain replenishment fields (avg_daily_sales
    through stock_risk) onto this same table rather than a parallel one,
    since it's computed in the same generation pass as everything else.
    """
    __tablename__ = "demand_forecasts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True)
    category_id = Column(UUID(as_uuid=False), ForeignKey("categories.id", ondelete="CASCADE"), nullable=True, index=True)

    forecast_period = Column(SAEnum(ForecastPeriod), nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    historical_sales = Column(Integer, nullable=False, default=0)
    predicted_demand = Column(Integer, nullable=False, default=0)
    confidence_score = Column(Numeric(5, 4), nullable=False, default=0)  # 0.0000 - 1.0000
    expected_growth_percentage = Column(Numeric(7, 2), nullable=False, default=0)

    # Product-level snapshot fields, used to compute the recommendation
    # without re-hitting the Inventory table on every read.
    current_stock = Column(Integer, nullable=True)
    reorder_level = Column(Integer, nullable=True)
    recommendation = Column(SAEnum(RecommendationType), nullable=True)

    # ---- Task 11: Inventory Forecasting & Smart Replenishment ----
    avg_daily_sales = Column(Numeric(10, 4), nullable=True)
    # NULL means "infinite" (zero average daily sales, so stock never runs out).
    days_of_stock_remaining = Column(Numeric(10, 2), nullable=True)
    lead_time_days = Column(Integer, nullable=True)
    safety_stock = Column(Integer, nullable=True)
    reorder_point = Column(Integer, nullable=True)
    recommended_reorder_quantity = Column(Integer, nullable=True)
    stock_risk = Column(SAEnum(StockRisk), nullable=True)

    # Cached copy of this forecast's most recent accuracy score (same value
    # as the newest ForecastHistory.accuracy row for this forecast). Kept
    # here too, rather than only in ForecastHistory, so the product list can
    # sort/filter by accuracy without a join — NULL until a forecast period
    # has actually elapsed and been scored at least once.
    last_accuracy = Column(Numeric(5, 4), nullable=True)

    generated_by = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    product = relationship("Product")
    category = relationship("Category")
    generator = relationship("User")
    history_entries = relationship("ForecastHistory", back_populates="forecast", cascade="all, delete-orphan")


class ForecastHistory(Base):
    """
    Accuracy audit trail. When a forecast is refreshed and its previous
    target period has fully elapsed, we compare what actually sold during
    that window against what was predicted and log the result here.
    """
    __tablename__ = "forecast_history"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    forecast_id = Column(UUID(as_uuid=False), ForeignKey("demand_forecasts.id", ondelete="CASCADE"), nullable=False, index=True)
    historical_sales = Column(Integer, nullable=False)   # actual sales observed during the forecasted window
    prediction = Column(Integer, nullable=False)         # what had been predicted for that window
    accuracy = Column(Numeric(5, 4), nullable=False)     # 0.0000 - 1.0000
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    forecast = relationship("DemandForecast", back_populates="history_entries")
