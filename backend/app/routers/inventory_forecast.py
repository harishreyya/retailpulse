from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, case, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    DemandForecast, ForecastPeriod, StockRisk, Product, User, UserRole,
)
from app.schemas.forecasting import (
    InventoryForecastRow, InventoryForecastListResponse, InventoryForecastSummary,
    InventoryForecastDetail, ComparisonMetric, ProductDemandTrendPoint,
)
from app.dependencies import require_roles, get_current_company_id
from app.services.forecasting import weekly_demand_series, forecast_demand_curve

router = APIRouter(prefix="/inventory-forecast", tags=["inventory-forecast"])

INVENTORY_FORECAST_ROLES = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST]

# Severity ordering used for the "Risk Level" sort — most urgent first.
RISK_SEVERITY = {
    StockRisk.OUT_OF_STOCK: 0,
    StockRisk.STOCKOUT_RISK: 1,
    StockRisk.LOW_STOCK: 2,
    StockRisk.HEALTHY: 3,
    StockRisk.OVERSTOCK: 4,
}


def _base_query(db: Session, company_id: str, forecast_period: ForecastPeriod):
    return db.query(DemandForecast).options(
        joinedload(DemandForecast.product), joinedload(DemandForecast.category),
    ).join(Product, DemandForecast.product_id == Product.id).filter(
        DemandForecast.company_id == company_id,
        DemandForecast.product_id.isnot(None),
        DemandForecast.forecast_period == forecast_period,
        DemandForecast.stock_risk.isnot(None),  # only rows that went through Task 11 calc
    )


def _serialize(f: DemandForecast) -> InventoryForecastRow:
    return InventoryForecastRow(
        forecast_id=f.id, product_id=f.product_id, product_name=f.product.name, sku=f.product.sku,
        category_name=f.category.name, supplier=getattr(f.product, "supplier", None),
        current_stock=f.current_stock or 0, avg_daily_sales=f.avg_daily_sales or Decimal("0"),
        forecasted_demand=f.predicted_demand, days_of_stock_remaining=f.days_of_stock_remaining,
        reorder_point=f.reorder_point or 0, recommended_reorder_quantity=f.recommended_reorder_quantity or 0,
        stock_risk=f.stock_risk, generated_at=f.generated_at,
    )


@router.get("", response_model=InventoryForecastListResponse)
def list_inventory_forecast(
    forecast_period: ForecastPeriod = Query(ForecastPeriod.NEXT_30_DAYS),
    stock_risk: Optional[StockRisk] = None,
    category_id: Optional[str] = None,
    supplier: Optional[str] = None,
    search: Optional[str] = None,
    reorder_required: Optional[bool] = None,
    sort_by: str = Query("risk_level", pattern="^(current_stock|forecasted_demand|days_remaining|recommended_quantity|risk_level)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(INVENTORY_FORECAST_ROLES)),
):
    query = _base_query(db, company_id, forecast_period)

    if stock_risk:
        query = query.filter(DemandForecast.stock_risk == stock_risk)
    if category_id:
        query = query.filter(DemandForecast.category_id == category_id)
    if supplier:
        query = query.filter(Product.supplier.ilike(f"%{supplier}%"))
    if search:
        like = f"%{search}%"
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if reorder_required is True:
        query = query.filter(DemandForecast.recommended_reorder_quantity > 0)
    elif reorder_required is False:
        query = query.filter(DemandForecast.recommended_reorder_quantity == 0)

    total = query.count()

    order_fn = asc if sort_dir == "asc" else desc
    if sort_by == "current_stock":
        query = query.order_by(order_fn(DemandForecast.current_stock))
    elif sort_by == "forecasted_demand":
        query = query.order_by(order_fn(DemandForecast.predicted_demand))
    elif sort_by == "days_remaining":
        query = query.order_by(order_fn(DemandForecast.days_of_stock_remaining))
    elif sort_by == "recommended_quantity":
        query = query.order_by(order_fn(DemandForecast.recommended_reorder_quantity))
    else:  # risk_level
        severity_case = case(
            (DemandForecast.stock_risk == StockRisk.OUT_OF_STOCK, 0),
            (DemandForecast.stock_risk == StockRisk.STOCKOUT_RISK, 1),
            (DemandForecast.stock_risk == StockRisk.LOW_STOCK, 2),
            (DemandForecast.stock_risk == StockRisk.HEALTHY, 3),
            (DemandForecast.stock_risk == StockRisk.OVERSTOCK, 4),
            else_=99,
        )
        query = query.order_by(order_fn(severity_case))

    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return InventoryForecastListResponse(items=[_serialize(f) for f in rows], total=total)


@router.get("/summary", response_model=InventoryForecastSummary)
def inventory_forecast_summary(
    forecast_period: ForecastPeriod = Query(ForecastPeriod.NEXT_30_DAYS),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(INVENTORY_FORECAST_ROLES)),
):
    rows = _base_query(db, company_id, forecast_period).all()

    return InventoryForecastSummary(
        products_requiring_reorder=sum(1 for f in rows if (f.recommended_reorder_quantity or 0) > 0),
        products_at_stockout_risk=sum(1 for f in rows if f.stock_risk == StockRisk.STOCKOUT_RISK),
        overstocked_products=sum(1 for f in rows if f.stock_risk == StockRisk.OVERSTOCK),
        healthy_products=sum(1 for f in rows if f.stock_risk == StockRisk.HEALTHY),
        out_of_stock_products=sum(1 for f in rows if f.stock_risk == StockRisk.OUT_OF_STOCK),
    )


@router.get("/{product_id}", response_model=InventoryForecastDetail)
def get_inventory_forecast_detail(
    product_id: str,
    forecast_period: ForecastPeriod = Query(ForecastPeriod.NEXT_30_DAYS),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(INVENTORY_FORECAST_ROLES)),
):
    forecast = _base_query(db, company_id, forecast_period).filter(
        DemandForecast.product_id == product_id
    ).first()
    if not forecast:
        raise HTTPException(
            status_code=404,
            detail="No inventory forecast found for this product/period. Generate a forecast first.",
        )

    row = _serialize(forecast)

    recommended_stock = (forecast.current_stock or 0) + (forecast.recommended_reorder_quantity or 0)
    comparison = [
        ComparisonMetric(
            metric="Stock", current=Decimal(forecast.current_stock or 0), recommended=Decimal(recommended_stock),
            action_required=(forecast.recommended_reorder_quantity or 0) > 0,
        ),
        ComparisonMetric(
            metric="Daily Demand", current=forecast.avg_daily_sales or Decimal("0"),
            recommended=forecast.avg_daily_sales or Decimal("0"), action_required=False,
        ),
        ComparisonMetric(
            metric="Reorder Point", current=Decimal(forecast.reorder_point or 0),
            recommended=Decimal(forecast.reorder_point or 0),
            action_required=(forecast.current_stock or 0) <= (forecast.reorder_point or 0),
        ),
        ComparisonMetric(
            metric="Safety Stock", current=Decimal(forecast.safety_stock or 0),
            recommended=Decimal(forecast.safety_stock or 0), action_required=False,
        ),
    ]

    horizon_days = (forecast.period_end - forecast.period_start).days or 1
    historical = [ProductDemandTrendPoint(**p) for p in weekly_demand_series(db, company_id, product_id)]
    curve = [ProductDemandTrendPoint(**p) for p in forecast_demand_curve(forecast.predicted_demand, horizon_days)]

    return InventoryForecastDetail(
        forecast=row, comparison=comparison,
        lead_time_days=forecast.lead_time_days or 0, safety_stock=forecast.safety_stock or 0,
        historical_demand=historical, forecasted_demand_curve=curve,
    )
