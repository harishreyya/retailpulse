from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Sale, SaleItem, Product, ProductStatus, Category, Inventory,
    DemandForecast, ForecastHistory, ForecastPeriod, RecommendationType, StockRisk,
    NotificationType, NotificationPriority,
)
from app.services.notifications import notify_roles, evaluate_stockout_risk

PERIOD_DAYS = {
    ForecastPeriod.NEXT_7_DAYS: 7,
    ForecastPeriod.NEXT_30_DAYS: 30,
    ForecastPeriod.NEXT_90_DAYS: 90,
}

# How far back we look for the "recent" and "prior" trend windows, used to
# derive a simple growth rate (a lightweight stand-in for a full regression).
TREND_WINDOW_DAYS = 30
# How much historical data we require before we'll even attempt a forecast.
MIN_HISTORY_DAYS = 14
GROWTH_NOTIFICATION_THRESHOLD = Decimal("25")  # % growth that counts as "significant"

# ---- Task 11: Inventory Forecasting & Smart Replenishment constants ----
# This app has no supplier lead-time data yet (no `lead_time_days` field on
# Product/Supplier), so we use a documented default. If/when real supplier
# lead times are added, swap this constant for that field.
DEFAULT_LEAD_TIME_DAYS = 7
# Safety stock = buffer against demand variability, expressed as N days of
# average demand held in reserve on top of what lead time alone requires.
SAFETY_STOCK_DAYS = 3
# A product is flagged OVERSTOCK when current stock exceeds this multiple of
# (reorder point + forecasted demand) — i.e. holding roughly double or more
# of what's needed to comfortably cover the next reorder cycle.
OVERSTOCK_MULTIPLIER = Decimal("2.0")


def _daily_sales(db: Session, company_id: str, product_id: str, start: datetime, end: datetime) -> int:
    total = db.query(func.coalesce(func.sum(SaleItem.quantity), 0)).join(
        Sale, SaleItem.sale_id == Sale.id
    ).filter(
        Sale.company_id == company_id, SaleItem.product_id == product_id,
        Sale.sale_date >= start, Sale.sale_date < end,
    ).scalar()
    return int(total or 0)


def _batch_sales_windows(
    db: Session, company_id: str, product_ids: list[str],
    recent_start: datetime, prior_start: datetime, period_start: datetime,
) -> dict[str, dict]:
    """
    Replaces what used to be 2-3 separate `_daily_sales()` calls PER PRODUCT
    inside the generation loop (mentor review: "calls the sales query 3-4
    times per product"). Instead, this runs exactly 2 grouped SUM queries
    (recent window, prior window) covering every product in the batch at
    once, regardless of how many products there are.

    `total_history` = recent + prior always holds, because the caller sets
    `prior_start = history_start` explicitly (see generate_forecasts) — so
    the old third "total history" query was always redundant with these
    two and is dropped entirely.
    """
    if not product_ids:
        return {}

    def _grouped_sum(start: datetime, end: datetime) -> dict[str, int]:
        rows = (
            db.query(SaleItem.product_id, func.coalesce(func.sum(SaleItem.quantity), 0))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .filter(
                Sale.company_id == company_id, SaleItem.product_id.in_(product_ids),
                Sale.sale_date >= start, Sale.sale_date < end,
            )
            .group_by(SaleItem.product_id)
            .all()
        )
        return {pid: int(qty) for pid, qty in rows}

    recent_by_product = _grouped_sum(recent_start, period_start)
    prior_by_product = _grouped_sum(prior_start, recent_start)

    weeks_rows = (
        db.query(SaleItem.product_id, func.count(func.distinct(func.date_trunc("week", Sale.sale_date))))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.company_id == company_id, SaleItem.product_id.in_(product_ids),
            Sale.sale_date >= prior_start, Sale.sale_date < period_start,
        )
        .group_by(SaleItem.product_id)
        .all()
    )
    weeks_by_product = {pid: int(cnt) for pid, cnt in weeks_rows}

    windows = {}
    for pid in product_ids:
        recent = recent_by_product.get(pid, 0)
        prior = prior_by_product.get(pid, 0)
        windows[pid] = {
            "total_history": recent + prior,
            "recent_sales": recent,
            "prior_sales": prior,
            "weeks_with_sales": weeks_by_product.get(pid, 0),
        }
    return windows


def _batch_actual_sales_for_existing(
    db: Session, company_id: str, existing_by_product: dict[str, "DemandForecast"],
) -> dict[str, int]:
    """
    For every existing forecast whose target period has already elapsed,
    batch-fetches the actual sales for that exact window — grouped by the
    distinct (period_start, period_end) pairs involved, so this is one
    query per distinct window (in practice almost always just 1, since a
    whole generation run shares the same window) rather than one query
    per product.
    """
    now = datetime.utcnow()
    windows: dict[tuple, list[str]] = {}
    for pid, forecast in existing_by_product.items():
        if forecast.period_end <= now:
            windows.setdefault((forecast.period_start, forecast.period_end), []).append(pid)

    actuals: dict[str, int] = {}
    for (start, end), pids in windows.items():
        for pid in pids:
            actuals[pid] = 0  # default so "no matching sales" is 0, not missing
        rows = (
            db.query(SaleItem.product_id, func.coalesce(func.sum(SaleItem.quantity), 0))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .filter(
                Sale.company_id == company_id, SaleItem.product_id.in_(pids),
                Sale.sale_date >= start, Sale.sale_date < end,
            )
            .group_by(SaleItem.product_id)
            .all()
        )
        for pid, qty in rows:
            actuals[pid] = int(qty)
    return actuals


def _compute_recommendation(current_stock: int, reorder_level: int, predicted_demand: int) -> RecommendationType:
    """Task 7's original 4-tier recommendation. Kept as-is so the existing
    Demand Forecasting dashboard/notifications/export keep working."""
    if current_stock <= 0:
        return RecommendationType.IMMEDIATE_RESTOCK_REQUIRED
    if current_stock < predicted_demand and current_stock <= reorder_level:
        return RecommendationType.IMMEDIATE_RESTOCK_REQUIRED
    if current_stock <= reorder_level:
        return RecommendationType.REORDER_SOON
    if current_stock > predicted_demand * 2 and current_stock > reorder_level * 3:
        return RecommendationType.OVERSTOCK_RISK
    return RecommendationType.STOCK_HEALTHY


def compute_replenishment(
    current_stock: int, avg_daily_sales: Decimal, forecasted_demand: int,
    lead_time_days: int = DEFAULT_LEAD_TIME_DAYS,
) -> dict:
    """
    Task 11's supply-chain calculations. Documented formulas:

    safety_stock       = avg_daily_sales * SAFETY_STOCK_DAYS
                          (buffer for demand variability during lead time)

    reorder_point       = (avg_daily_sales * lead_time_days) + safety_stock
                          (stock level at which a new order should be placed,
                           so it arrives — on average — before you run out)

    days_of_stock_remaining = current_stock / avg_daily_sales
                          (None/"infinite" when avg_daily_sales == 0)

    recommended_reorder_quantity = max(0, forecasted_demand + safety_stock - current_stock)
                          when current_stock <= reorder_point, else 0.
                          i.e. order enough to cover the forecasted demand
                          for the period plus the safety buffer, net of
                          what's already on hand.

    stock_risk (5-tier), evaluated in this order:
      OUT_OF_STOCK   current_stock <= 0
      STOCKOUT_RISK  days_of_stock_remaining is not None AND
                     days_of_stock_remaining < lead_time_days
                     (will hit zero before a fresh order could even arrive)
      LOW_STOCK      current_stock <= reorder_point
      OVERSTOCK      current_stock > (reorder_point + forecasted_demand) * OVERSTOCK_MULTIPLIER
      HEALTHY        everything else
    """
    safety_stock = int(round(avg_daily_sales * SAFETY_STOCK_DAYS))
    reorder_point = int(round(avg_daily_sales * lead_time_days)) + safety_stock

    days_of_stock_remaining: Optional[Decimal] = None
    if avg_daily_sales > 0:
        days_of_stock_remaining = (Decimal(current_stock) / avg_daily_sales).quantize(Decimal("0.01"))

    needs_reorder = current_stock <= reorder_point
    recommended_reorder_quantity = 0
    if needs_reorder:
        recommended_reorder_quantity = max(0, forecasted_demand + safety_stock - current_stock)

    if current_stock <= 0:
        stock_risk = StockRisk.OUT_OF_STOCK
    elif days_of_stock_remaining is not None and days_of_stock_remaining < lead_time_days:
        stock_risk = StockRisk.STOCKOUT_RISK
    elif current_stock <= reorder_point:
        stock_risk = StockRisk.LOW_STOCK
    elif Decimal(current_stock) > (Decimal(reorder_point + forecasted_demand) * OVERSTOCK_MULTIPLIER):
        stock_risk = StockRisk.OVERSTOCK
    else:
        stock_risk = StockRisk.HEALTHY

    return {
        "lead_time_days": lead_time_days,
        "safety_stock": safety_stock,
        "reorder_point": reorder_point,
        "days_of_stock_remaining": days_of_stock_remaining,
        "recommended_reorder_quantity": recommended_reorder_quantity,
        "stock_risk": stock_risk,
    }


def _forecast_one_product(
    db: Session, company_id: str, product: Product, period: ForecastPeriod,
    period_start: datetime, period_end: datetime, user_id: Optional[str],
    sales_window: dict, inventory: Optional[Inventory],
    existing: Optional[DemandForecast], actual_for_existing: Optional[int],
) -> Optional[DemandForecast]:
    horizon_days = (period_end - period_start).days or 1

    total_history = sales_window["total_history"]
    if total_history <= 0:
        return None  # no historical sales data -> nothing to forecast from

    recent_sales = sales_window["recent_sales"]
    prior_sales = sales_window["prior_sales"]
    weeks_with_sales = sales_window["weeks_with_sales"]

    avg_daily_recent = recent_sales / TREND_WINDOW_DAYS
    if prior_sales > 0:
        growth_rate = (recent_sales - prior_sales) / prior_sales
    else:
        growth_rate = 0.5 if recent_sales > 0 else 0.0
    growth_rate = max(-0.5, min(growth_rate, 1.0))  # clamp to a sane range

    predicted_demand = max(0, round(avg_daily_recent * horizon_days * (1 + growth_rate)))

    confidence = min(Decimal("0.95"), Decimal("0.30") + Decimal("0.60") * Decimal(min(weeks_with_sales, 13)) / Decimal(13))

    current_stock = inventory.available_stock if inventory else product.stock_quantity
    reorder_level = inventory.reorder_level if inventory else 10
    recommendation = _compute_recommendation(current_stock, reorder_level, predicted_demand)

    avg_daily_sales_decimal = Decimal(str(round(avg_daily_recent, 4)))
    replenishment = compute_replenishment(current_stock, avg_daily_sales_decimal, predicted_demand)

    # Log accuracy for the previous forecast if its window has already elapsed.
    if existing and existing.period_end <= datetime.utcnow() and actual_for_existing is not None:
        actual = actual_for_existing
        denom = max(actual, existing.predicted_demand, 1)
        accuracy = Decimal(1) - (Decimal(abs(actual - existing.predicted_demand)) / Decimal(denom))
        accuracy = max(Decimal(0), min(accuracy, Decimal(1)))
        db.add(ForecastHistory(
            forecast_id=existing.id, historical_sales=actual,
            prediction=existing.predicted_demand, accuracy=accuracy,
        ))
        existing.last_accuracy = accuracy

    growth_pct = Decimal(growth_rate * 100).quantize(Decimal("0.01"))

    if existing:
        forecast = existing
        forecast.period_start = period_start
        forecast.period_end = period_end
        forecast.historical_sales = total_history
        forecast.predicted_demand = predicted_demand
        forecast.confidence_score = confidence
        forecast.expected_growth_percentage = growth_pct
        forecast.current_stock = current_stock
        forecast.reorder_level = reorder_level
        forecast.recommendation = recommendation
    else:
        forecast = DemandForecast(
            company_id=company_id, product_id=product.id, category_id=product.category_id,
            forecast_period=period, period_start=period_start, period_end=period_end,
            historical_sales=total_history, predicted_demand=predicted_demand,
            confidence_score=confidence, expected_growth_percentage=growth_pct,
            current_stock=current_stock, reorder_level=reorder_level,
            recommendation=recommendation,
        )
        db.add(forecast)

    forecast.generated_by = user_id
    forecast.generated_at = datetime.utcnow()
    forecast.avg_daily_sales = avg_daily_sales_decimal
    forecast.days_of_stock_remaining = replenishment["days_of_stock_remaining"]
    forecast.lead_time_days = replenishment["lead_time_days"]
    forecast.safety_stock = replenishment["safety_stock"]
    forecast.reorder_point = replenishment["reorder_point"]
    forecast.recommended_reorder_quantity = replenishment["recommended_reorder_quantity"]
    forecast.stock_risk = replenishment["stock_risk"]

    db.flush()
    _maybe_notify(db, company_id, product, forecast)
    return forecast


def _maybe_notify(db: Session, company_id: str, product: Product, forecast: DemandForecast):
    if forecast.recommendation == RecommendationType.IMMEDIATE_RESTOCK_REQUIRED:
        notify_roles(
            db, company_id, NotificationType.FORECAST_STOCK_RUNOUT,
            title="Predicted Stockout",
            message=f"{product.name} is predicted to run out of stock before the forecast period ends.",
            priority=NotificationPriority.HIGH,
            product_id=product.id, resource_type="Product", resource_id=product.id,
            dedupe_key=f"forecast:{product.id}:stock_runout:{forecast.forecast_period.value}",
        )
    if forecast.predicted_demand > (forecast.current_stock or 0):
        notify_roles(
            db, company_id, NotificationType.FORECAST_DEMAND_EXCEEDS_STOCK,
            title="Demand Exceeds Stock",
            message=f"Forecasted demand for {product.name} ({forecast.predicted_demand}) exceeds available stock ({forecast.current_stock or 0}).",
            priority=NotificationPriority.MEDIUM,
            product_id=product.id, resource_type="Product", resource_id=product.id,
            dedupe_key=f"forecast:{product.id}:demand_exceeds_stock:{forecast.forecast_period.value}",
        )
    if forecast.expected_growth_percentage >= GROWTH_NOTIFICATION_THRESHOLD:
        notify_roles(
            db, company_id, NotificationType.FORECAST_DEMAND_GROWTH,
            title="Demand Growth Detected",
            message=f"{product.name} shows {forecast.expected_growth_percentage}% demand growth in the latest forecast.",
            priority=NotificationPriority.LOW,
            product_id=product.id, resource_type="Product", resource_id=product.id,
            dedupe_key=f"forecast:{product.id}:demand_growth:{forecast.forecast_period.value}",
        )
    # Task 14: predictive stockout-risk alert, using the replenishment
    # numbers this same forecast just computed.
    evaluate_stockout_risk(db, company_id, product, forecast.days_of_stock_remaining, forecast.lead_time_days or DEFAULT_LEAD_TIME_DAYS)


def _resolve_period_window(period: ForecastPeriod, custom_start=None, custom_end=None):
    now = datetime.utcnow()
    if period == ForecastPeriod.CUSTOM:
        if not custom_start or not custom_end:
            raise ValueError("period_start and period_end are required for a CUSTOM forecast")
        start = datetime.combine(custom_start, datetime.min.time())
        end = datetime.combine(custom_end, datetime.max.time())
        if end <= start:
            raise ValueError("period_end must be after period_start")
        return start, end
    return now, now + timedelta(days=PERIOD_DAYS[period])


def generate_forecasts(
    db: Session, company_id: str, period: ForecastPeriod, user_id: Optional[str],
    category_id: Optional[str] = None, custom_start=None, custom_end=None,
) -> dict:
    period_start, period_end = _resolve_period_window(period, custom_start, custom_end)

    query = db.query(Product).filter(Product.company_id == company_id, Product.status == ProductStatus.ACTIVE)
    if category_id:
        query = query.filter(Product.category_id == category_id)
    products = query.all()
    product_ids = [p.id for p in products]

    # prior_start is deliberately set equal to history_start (not derived
    # from TREND_WINDOW_DAYS alone) so that recent+prior always equals the
    # full history window, even if MIN_HISTORY_DAYS and TREND_WINDOW_DAYS
    # are changed independently later — see _batch_sales_windows docstring.
    history_start = period_start - timedelta(days=max(TREND_WINDOW_DAYS * 2, MIN_HISTORY_DAYS))
    recent_start = period_start - timedelta(days=TREND_WINDOW_DAYS)
    prior_start = history_start

    # Everything below is fetched ONCE for the whole batch (mentor review:
    # the old version re-ran 3-4 sales queries per product inside the loop).
    sales_windows = _batch_sales_windows(db, company_id, product_ids, recent_start, prior_start, period_start)

    inventory_by_product = {
        inv.product_id: inv
        for inv in db.query(Inventory).filter(
            Inventory.company_id == company_id, Inventory.product_id.in_(product_ids)
        ).all()
    } if product_ids else {}

    existing_by_product: dict[str, DemandForecast] = {}
    if product_ids:
        existing_query = db.query(DemandForecast).filter(
            DemandForecast.company_id == company_id, DemandForecast.forecast_period == period,
            DemandForecast.product_id.in_(product_ids),
        )
        if period == ForecastPeriod.CUSTOM:
            existing_query = existing_query.filter(DemandForecast.period_start == period_start)
        for f in existing_query.all():
            existing_by_product[f.product_id] = f

    actuals_for_existing = _batch_actual_sales_for_existing(db, company_id, existing_by_product)

    empty_window = {"total_history": 0, "recent_sales": 0, "prior_sales": 0, "weeks_with_sales": 0}
    forecasted = 0
    skipped = 0
    touched_category_ids = set()

    for product in products:
        result = _forecast_one_product(
            db, company_id, product, period, period_start, period_end, user_id,
            sales_window=sales_windows.get(product.id, empty_window),
            inventory=inventory_by_product.get(product.id),
            existing=existing_by_product.get(product.id),
            actual_for_existing=actuals_for_existing.get(product.id),
        )
        if result:
            forecasted += 1
            touched_category_ids.add(product.category_id)
        else:
            skipped += 1

    categories_forecasted = 0
    for category_id_ in touched_category_ids:
        if _forecast_category(db, company_id, category_id_, period, period_start, period_end, user_id):
            categories_forecasted += 1

    db.commit()
    return {
        "products_forecasted": forecasted,
        "categories_forecasted": categories_forecasted,
        "skipped_no_history": skipped,
    }


def _forecast_category(
    db: Session, company_id: str, category_id: str, period: ForecastPeriod,
    period_start: datetime, period_end: datetime, user_id: Optional[str],
) -> bool:
    product_rows = db.query(DemandForecast).filter(
        DemandForecast.company_id == company_id, DemandForecast.category_id == category_id,
        DemandForecast.product_id.isnot(None), DemandForecast.forecast_period == period,
        DemandForecast.period_start == period_start,
    ).all()
    if not product_rows:
        return False

    total_historical = sum(r.historical_sales for r in product_rows)
    total_predicted = sum(r.predicted_demand for r in product_rows)
    avg_growth = sum(r.expected_growth_percentage for r in product_rows) / len(product_rows)

    existing_query = db.query(DemandForecast).filter(
        DemandForecast.company_id == company_id, DemandForecast.category_id == category_id,
        DemandForecast.product_id.is_(None), DemandForecast.forecast_period == period,
    )
    if period == ForecastPeriod.CUSTOM:
        existing_query = existing_query.filter(DemandForecast.period_start == period_start)
    existing = existing_query.first()

    if existing:
        existing.period_start = period_start
        existing.period_end = period_end
        existing.historical_sales = total_historical
        existing.predicted_demand = total_predicted
        existing.expected_growth_percentage = avg_growth
        existing.generated_by = user_id
        existing.generated_at = datetime.utcnow()
    else:
        db.add(DemandForecast(
            company_id=company_id, product_id=None, category_id=category_id,
            forecast_period=period, period_start=period_start, period_end=period_end,
            historical_sales=total_historical, predicted_demand=total_predicted,
            confidence_score=Decimal("0"), expected_growth_percentage=avg_growth,
            generated_by=user_id,
        ))
    db.flush()
    return True


def weekly_demand_series(db: Session, company_id: str, product_id: str, weeks: int = 8) -> list[dict]:
    """Historical weekly-quantity-sold series, most recent `weeks` weeks,
    for the required forecast visualization."""
    now = datetime.utcnow()
    points = []
    for i in range(weeks - 1, -1, -1):
        start = now - timedelta(days=(i + 1) * 7)
        end = now - timedelta(days=i * 7)
        qty = _daily_sales(db, company_id, product_id, start, end)
        points.append({"period": start.strftime("%b %d"), "predicted_demand": qty})
    return points


def forecast_demand_curve(predicted_demand: int, horizon_days: int, buckets: int = 4) -> list[dict]:
    """
    Distributes predicted_demand evenly across `buckets` points spanning the
    forecast horizon, for charting alongside the historical series. This is
    a straight-line projection for visualization only — the single
    predicted_demand total (not this curve) is what recommendations are
    calculated from.
    """
    per_bucket = predicted_demand / buckets if buckets else predicted_demand
    days_per_bucket = max(horizon_days // buckets, 1)
    points = []
    for i in range(buckets):
        points.append({
            "period": f"Day {i * days_per_bucket + 1}-{(i + 1) * days_per_bucket}",
            "predicted_demand": round(per_bucket),
        })
    return points
