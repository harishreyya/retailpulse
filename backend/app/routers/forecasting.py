import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, asc, desc
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    DemandForecast, ForecastHistory, ForecastPeriod, RecommendationType,
    Product, Category, User, UserRole, ProductStatus, Sale, SaleItem,
)
from app.schemas import (
    ForecastGenerateRequest, ForecastGenerateResponse,
    ProductForecastRow, ProductForecastListResponse,
    CategoryForecastRow, CategoryForecastListResponse,
    ForecastKPIs, HistoricalVsForecastPoint, ProductDemandTrendPoint,
    CategoryDemandTrendRow, TopPredictedProductRow, SeasonalPatternPoint,
    ForecastAnalyticsSummary, RecommendationRow,
)
from app.dependencies import require_roles, get_current_company_id
from app.audit import log_action
from app.services.forecasting import generate_forecasts

router = APIRouter(prefix="/forecasts", tags=["forecasting"])

FORECAST_ROLES = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST]

SORT_FIELDS = {
    "predicted_demand": DemandForecast.predicted_demand,
    "lowest_stock": DemandForecast.current_stock,
    "growth": DemandForecast.expected_growth_percentage,
    "accuracy": DemandForecast.last_accuracy,
}


def _serialize_product_row(f: DemandForecast) -> ProductForecastRow:
    return ProductForecastRow(
        forecast_id=f.id, product_id=f.product_id, product_name=f.product.name, sku=f.product.sku,
        brand=f.product.brand, category_id=f.category_id, category_name=f.category.name,
        current_stock=f.current_stock or 0, historical_sales=f.historical_sales,
        predicted_demand=f.predicted_demand, forecast_period=f.forecast_period,
        period_start=f.period_start, period_end=f.period_end, confidence_score=f.confidence_score,
        expected_growth_percentage=f.expected_growth_percentage, recommendation=f.recommendation,
        generated_at=f.generated_at, last_accuracy=f.last_accuracy,
    )


# ---------- Generate / Refresh ----------

@router.post("/generate", response_model=ForecastGenerateResponse)
def generate(
    payload: ForecastGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(FORECAST_ROLES)),
):
    is_refresh = db.query(DemandForecast.id).filter(DemandForecast.company_id == company_id).first() is not None

    try:
        result = generate_forecasts(
            db, company_id, payload.forecast_period, current_user.id,
            category_id=payload.category_id,
            custom_start=payload.period_start, custom_end=payload.period_end,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if result["products_forecasted"] == 0 and result["skipped_no_history"] > 0:
        # Nothing could be forecasted at all (validation: requires historical sales data).
        pass

    action = "Forecast Refreshed" if is_refresh else "Forecast Generated"
    log_action(db, request, action, company_id=company_id, user_id=current_user.id,
               entity_name=f"{payload.forecast_period.value}",
               details=f"products={result['products_forecasted']}, categories={result['categories_forecasted']}, skipped={result['skipped_no_history']}")
    log_action(db, request, "Inventory Recommendation Generated", company_id=company_id, user_id=current_user.id,
               entity_name=f"{payload.forecast_period.value}",
               details=f"{result['products_forecasted']} product recommendations refreshed")
    db.commit()

    return ForecastGenerateResponse(**result)


# ---------- Product level ----------

@router.get("/products", response_model=ProductForecastListResponse)
def list_product_forecasts(
    forecast_period: ForecastPeriod = Query(ForecastPeriod.NEXT_30_DAYS),
    search: Optional[str] = None,
    category_id: Optional[str] = None,
    brand: Optional[str] = None,
    recommendation: Optional[RecommendationType] = None,
    sort_by: str = Query("predicted_demand", pattern="^(predicted_demand|lowest_stock|growth|accuracy)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(FORECAST_ROLES)),
):
    query = db.query(DemandForecast).options(
        joinedload(DemandForecast.product), joinedload(DemandForecast.category),
    ).join(Product, DemandForecast.product_id == Product.id).filter(
        DemandForecast.company_id == company_id,
        DemandForecast.product_id.isnot(None),
        DemandForecast.forecast_period == forecast_period,
    )

    if search:
        like = f"%{search}%"
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if category_id:
        query = query.filter(DemandForecast.category_id == category_id)
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    if recommendation:
        query = query.filter(DemandForecast.recommendation == recommendation)

    total = query.count()
    order_fn = asc if sort_dir == "asc" else desc
    sort_col = SORT_FIELDS[sort_by]
    query = query.order_by(order_fn(sort_col))
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    return ProductForecastListResponse(items=[_serialize_product_row(f) for f in rows], total=total)


# ---------- Category level ----------

@router.get("/categories", response_model=CategoryForecastListResponse)
def list_category_forecasts(
    forecast_period: ForecastPeriod = Query(ForecastPeriod.NEXT_30_DAYS),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(FORECAST_ROLES)),
):
    rows = db.query(DemandForecast).options(joinedload(DemandForecast.category)).filter(
        DemandForecast.company_id == company_id,
        DemandForecast.product_id.is_(None),
        DemandForecast.forecast_period == forecast_period,
    ).order_by(DemandForecast.predicted_demand.desc()).all()

    return CategoryForecastListResponse(items=[
        CategoryForecastRow(
            forecast_id=f.id, category_id=f.category_id, category_name=f.category.name,
            total_historical_sales=f.historical_sales, predicted_demand=f.predicted_demand,
            expected_growth_percentage=f.expected_growth_percentage, generated_at=f.generated_at,
        )
        for f in rows
    ])


# ---------- Recommendations ----------

@router.get("/recommendations", response_model=list[RecommendationRow])
def list_recommendations(
    forecast_period: ForecastPeriod = Query(ForecastPeriod.NEXT_30_DAYS),
    recommendation: Optional[RecommendationType] = None,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(FORECAST_ROLES)),
):
    query = db.query(DemandForecast).options(
        joinedload(DemandForecast.product), joinedload(DemandForecast.category),
    ).filter(
        DemandForecast.company_id == company_id, DemandForecast.product_id.isnot(None),
        DemandForecast.forecast_period == forecast_period,
        DemandForecast.recommendation.isnot(None),
    )
    if recommendation:
        query = query.filter(DemandForecast.recommendation == recommendation)
    else:
        query = query.filter(DemandForecast.recommendation != RecommendationType.STOCK_HEALTHY)

    rows = query.order_by(DemandForecast.current_stock.asc()).all()
    return [
        RecommendationRow(
            forecast_id=f.id, product_id=f.product_id, product_name=f.product.name, sku=f.product.sku,
            category_name=f.category.name, current_stock=f.current_stock or 0, reorder_level=f.reorder_level,
            predicted_demand=f.predicted_demand, recommendation=f.recommendation,
        )
        for f in rows
    ]


# ---------- Analytics ----------

@router.get("/analytics/summary", response_model=ForecastAnalyticsSummary)
def get_forecast_analytics(
    forecast_period: ForecastPeriod = Query(ForecastPeriod.NEXT_30_DAYS),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(FORECAST_ROLES)),
):
    product_forecasts = db.query(DemandForecast).options(
        joinedload(DemandForecast.product), joinedload(DemandForecast.category),
    ).filter(
        DemandForecast.company_id == company_id, DemandForecast.product_id.isnot(None),
        DemandForecast.forecast_period == forecast_period,
    ).all()

    total_predicted_demand = sum(f.predicted_demand for f in product_forecasts)
    products_run_out = sum(1 for f in product_forecasts if f.recommendation == RecommendationType.IMMEDIATE_RESTOCK_REQUIRED)
    high_growth = sum(1 for f in product_forecasts if f.expected_growth_percentage >= Decimal("25"))
    slow_moving = sum(1 for f in product_forecasts if f.expected_growth_percentage <= Decimal("-15"))

    accuracy_rows = db.query(ForecastHistory).join(
        DemandForecast, ForecastHistory.forecast_id == DemandForecast.id
    ).filter(DemandForecast.company_id == company_id).all()
    forecast_accuracy = (
        sum(r.accuracy for r in accuracy_rows) / len(accuracy_rows) if accuracy_rows else Decimal("0")
    )

    kpis = ForecastKPIs(
        total_predicted_demand=total_predicted_demand,
        products_expected_to_run_out=products_run_out,
        high_growth_products=high_growth,
        slow_moving_products=slow_moving,
        forecast_accuracy=forecast_accuracy,
    )

    period_label = forecast_period.value.replace("_", " ").title()
    historical_vs_forecast = [HistoricalVsForecastPoint(
        period=period_label,
        historical_sales=sum(f.historical_sales for f in product_forecasts),
        predicted_demand=total_predicted_demand,
    )]

    product_demand_trend = sorted(
        [ProductDemandTrendPoint(period=f.product.name, predicted_demand=f.predicted_demand) for f in product_forecasts],
        key=lambda p: p.predicted_demand, reverse=True,
    )[:15]

    by_category = defaultdict(lambda: {"predicted": 0, "historical": 0})
    for f in product_forecasts:
        by_category[f.category.name]["predicted"] += f.predicted_demand
        by_category[f.category.name]["historical"] += f.historical_sales
    category_demand_trend = [
        CategoryDemandTrendRow(category_name=name, predicted_demand=v["predicted"], historical_sales=v["historical"])
        for name, v in by_category.items()
    ]

    top_predicted_products = [
        TopPredictedProductRow(product_name=f.product.name, predicted_demand=f.predicted_demand)
        for f in sorted(product_forecasts, key=lambda x: x.predicted_demand, reverse=True)[:10]
    ]

    # Seasonal pattern: total actual sales quantity by calendar month over the last 12 months.
    twelve_months_ago = datetime.utcnow() - timedelta(days=365)
    monthly_rows = db.query(Sale.sale_date, SaleItem.quantity).join(
        SaleItem, SaleItem.sale_id == Sale.id
    ).filter(Sale.company_id == company_id, Sale.sale_date >= twelve_months_ago).all()
    monthly_totals = defaultdict(int)
    for sale_date, qty in monthly_rows:
        monthly_totals[sale_date.strftime("%b")] += qty
    month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    seasonal_pattern = [SeasonalPatternPoint(month=m, total_sales=monthly_totals.get(m, 0)) for m in month_order]

    return ForecastAnalyticsSummary(
        kpis=kpis,
        historical_vs_forecast=historical_vs_forecast,
        product_demand_trend=product_demand_trend,
        category_demand_trend=category_demand_trend,
        top_predicted_products=top_predicted_products,
        seasonal_pattern=seasonal_pattern,
    )


# ---------- Export ----------

@router.get("/export")
def export_forecasts(
    report: str = Query(..., pattern="^(products|categories)$"),
    format: str = Query(..., pattern="^(csv|pdf)$"),
    forecast_period: ForecastPeriod = Query(ForecastPeriod.NEXT_30_DAYS),
    request: Request = None,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(FORECAST_ROLES)),
):
    if report == "products":
        rows = db.query(DemandForecast).options(
            joinedload(DemandForecast.product), joinedload(DemandForecast.category),
        ).filter(
            DemandForecast.company_id == company_id, DemandForecast.product_id.isnot(None),
            DemandForecast.forecast_period == forecast_period,
        ).order_by(DemandForecast.predicted_demand.desc()).all()
        headers = ["Product", "SKU", "Category", "Current Stock", "Historical Sales",
                   "Predicted Demand", "Confidence", "Growth %", "Recommendation"]
        data_rows = [[
            f.product.name, f.product.sku, f.category.name, f.current_stock or 0, f.historical_sales,
            f.predicted_demand, str(f.confidence_score), str(f.expected_growth_percentage), f.recommendation.value if f.recommendation else "",
        ] for f in rows]
        filename = f"product_forecast.{format}"
    else:
        rows = db.query(DemandForecast).options(joinedload(DemandForecast.category)).filter(
            DemandForecast.company_id == company_id, DemandForecast.product_id.is_(None),
            DemandForecast.forecast_period == forecast_period,
        ).order_by(DemandForecast.predicted_demand.desc()).all()
        headers = ["Category", "Total Historical Sales", "Predicted Demand", "Growth %"]
        data_rows = [[
            f.category.name, f.historical_sales, f.predicted_demand, str(f.expected_growth_percentage),
        ] for f in rows]
        filename = f"category_forecast.{format}"

    log_action(db, request, "Forecast Exported", company_id=company_id, user_id=current_user.id,
               entity_name=f"{report}/{forecast_period.value}", details=f"format={format}, count={len(data_rows)}")
    db.commit()

    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(data_rows)
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF export requires the 'reportlab' package.")

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    title = "RetailPulse Product Forecast Report" if report == "products" else "RetailPulse Category Forecast Report"
    elements = [Paragraph(title, styles["Title"]), Spacer(1, 0.5 * cm)]
    table = Table([headers] + data_rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]))
    elements.append(table)
    doc.build(elements)
    pdf_buffer.seek(0)
    return StreamingResponse(
        pdf_buffer, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
