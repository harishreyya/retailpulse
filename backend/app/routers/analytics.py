import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_company_id, require_roles
from app.audit import log_action
from app.models import Sale, SaleItem, Product, Category, User, UserRole
from app.models.inventory import Inventory, StockStatus
from app.schemas.analytics import AnalyticsSummary, AnalyticsAuditEvent

router = APIRouter(prefix="/analytics", tags=["analytics"])

ANALYTICS_ROLES = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST]


def _matching_sale_ids(
    db: Session, company_id: str,
    date_from: Optional[date], date_to: Optional[date],
    category_id: Optional[str], product_id: Optional[str], brand: Optional[str],
    sales_channel: Optional[str], payment_method: Optional[str], customer_id: Optional[str],
):
    """
    A Sale.id query matching every filter. Sale-level filters (date,
    channel, payment method, customer) are applied directly on Sale.
    Item-level filters (category/product/brand) require a join against
    SaleItem/Product, but this query only ever selects Sale.id and is
    de-duplicated — so downstream order-level aggregates (SUM(total_amount),
    COUNT(*)) built from `Sale.id.in_(this)` never get fanned out just
    because a sale happens to have multiple matching line items.
    """
    query = db.query(Sale.id).filter(Sale.company_id == company_id)
    if date_from:
        query = query.filter(Sale.sale_date >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Sale.sale_date <= datetime.combine(date_to, datetime.max.time()))
    if sales_channel:
        query = query.filter(Sale.sales_channel == sales_channel)
    if payment_method:
        query = query.filter(Sale.payment_method == payment_method)
    if customer_id:
        query = query.filter(Sale.customer_id == customer_id)

    if category_id or product_id or brand:
        query = query.join(SaleItem, SaleItem.sale_id == Sale.id).join(Product, Product.id == SaleItem.product_id)
        if category_id:
            query = query.filter(SaleItem.category_id == category_id)
        if product_id:
            query = query.filter(SaleItem.product_id == product_id)
        if brand:
            query = query.filter(Product.brand == brand)
        query = query.distinct()

    return query


def _item_level_base(
    db: Session, company_id: str,
    date_from: Optional[date], date_to: Optional[date],
    category_id: Optional[str], product_id: Optional[str], brand: Optional[str],
    sales_channel: Optional[str], payment_method: Optional[str], customer_id: Optional[str],
):
    """
    SaleItem joined to Sale and Product, every filter applied directly.
    Safe to aggregate straight off this query for anything that is
    inherently per-line-item (quantity, discount, tax, per-product or
    per-category revenue) — each row already IS one line item, so no
    de-duplication is needed the way it is for order-level aggregates.
    Call `.with_entities(...)` on the result to pick columns/aggregates.
    """
    query = (
        db.query(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .filter(Sale.company_id == company_id)
    )
    if date_from:
        query = query.filter(Sale.sale_date >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Sale.sale_date <= datetime.combine(date_to, datetime.max.time()))
    if category_id:
        query = query.filter(SaleItem.category_id == category_id)
    if product_id:
        query = query.filter(SaleItem.product_id == product_id)
    if brand:
        query = query.filter(Product.brand == brand)
    if sales_channel:
        query = query.filter(Sale.sales_channel == sales_channel)
    if payment_method:
        query = query.filter(Sale.payment_method == payment_method)
    if customer_id:
        query = query.filter(Sale.customer_id == customer_id)
    return query


def _inventory_base_query(
    db: Session, company_id: str,
    category_id: Optional[str], product_id: Optional[str], brand: Optional[str],
):
    """Inventory + Product joined query. Date/channel/payment filters don't
    apply to inventory (it has no such dimensions) — only product/category/brand do.
    Call `.with_entities(...)` on the result to pick columns/aggregates."""
    query = (
        db.query(Inventory, Product)
        .join(Product, Product.id == Inventory.product_id)
        .filter(Inventory.company_id == company_id)
    )
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if product_id:
        query = query.filter(Product.id == product_id)
    if brand:
        query = query.filter(Product.brand == brand)
    return query


def _format_bucket_label(bucket: datetime, granularity: str) -> str:
    if granularity == "weekly":
        iso_year, iso_week, _ = bucket.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    if granularity == "monthly":
        return bucket.strftime("%Y-%m")
    return bucket.strftime("%Y-%m-%d")


def _build_summary(
    db: Session, company_id: str,
    date_from: Optional[date], date_to: Optional[date],
    category_id: Optional[str], product_id: Optional[str], brand: Optional[str],
    sales_channel: Optional[str], payment_method: Optional[str],
    granularity: str, customer_id: Optional[str] = None,
) -> AnalyticsSummary:
    filt_args = (date_from, date_to, category_id, product_id, brand, sales_channel, payment_method, customer_id)

    # --- Order-level KPIs (revenue, order count) ---
    # Aggregated straight off Sale, filtered to the matching-sale-id set, so
    # a sale with several matching line items is never counted more than once.
    total_revenue, total_orders = db.query(
        func.coalesce(func.sum(Sale.total_amount), 0),
        func.count(Sale.id),
    ).filter(Sale.id.in_(_matching_sale_ids(db, company_id, *filt_args))).one()
    total_revenue = Decimal(total_revenue)
    average_order_value = (total_revenue / total_orders) if total_orders else Decimal("0")

    # --- Item-level KPIs (quantity, discount, tax) ---
    total_products_sold, total_discount, total_tax = _item_level_base(
        db, company_id, *filt_args
    ).with_entities(
        func.coalesce(func.sum(SaleItem.quantity), 0),
        func.coalesce(func.sum(SaleItem.discount), 0),
        func.coalesce(func.sum(SaleItem.tax), 0),
    ).one()
    total_discount = Decimal(total_discount)
    total_tax = Decimal(total_tax)

    # --- Inventory KPIs ---
    total_inventory_value, low_stock_products, out_of_stock_products = _inventory_base_query(
        db, company_id, category_id, product_id, brand
    ).with_entities(
        func.coalesce(func.sum(Inventory.current_stock * Product.unit_price), 0),
        func.count(case((Inventory.stock_status == StockStatus.LOW_STOCK, 1))),
        func.count(case((Inventory.stock_status == StockStatus.OUT_OF_STOCK, 1))),
    ).one()
    total_inventory_value = Decimal(total_inventory_value)
    total_categories = db.query(Category).filter(Category.company_id == company_id).count()

    # --- Revenue trend ---
    trunc_unit = {"daily": "day", "weekly": "week", "monthly": "month"}.get(granularity, "day")
    bucket_expr = func.date_trunc(trunc_unit, Sale.sale_date)
    trend_rows = (
        db.query(bucket_expr.label("bucket"), func.sum(Sale.total_amount), func.count(Sale.id))
        .filter(Sale.id.in_(_matching_sale_ids(db, company_id, *filt_args)))
        .group_by(bucket_expr)
        .order_by(bucket_expr)
        .all()
    )
    revenue_trend = [
        {"period": _format_bucket_label(bucket, granularity), "revenue": Decimal(revenue or 0), "orders": orders}
        for bucket, revenue, orders in trend_rows
    ]

    # --- Top products ---
    top_products_rows = (
        _item_level_base(db, company_id, *filt_args)
        .with_entities(
            Product.id, Product.name, Product.sku,
            func.sum(SaleItem.quantity), func.sum(SaleItem.total),
        )
        .group_by(Product.id, Product.name, Product.sku)
        .order_by(func.sum(SaleItem.total).desc())
        .limit(10)
        .all()
    )
    top_products = [
        {"product_id": pid, "product_name": name, "sku": sku, "quantity_sold": qty, "revenue": Decimal(rev or 0)}
        for pid, name, sku, qty, rev in top_products_rows
    ]

    # --- Top categories --- (Category joined once here, instead of an
    # N+1 lookup per row like the previous implementation did.)
    top_categories_rows = (
        _item_level_base(db, company_id, *filt_args)
        .join(Category, Category.id == SaleItem.category_id, isouter=True)
        .with_entities(
            SaleItem.category_id, func.coalesce(Category.name, "Uncategorized"),
            func.sum(SaleItem.total), func.sum(SaleItem.quantity),
        )
        .group_by(SaleItem.category_id, Category.name)
        .order_by(func.sum(SaleItem.total).desc())
        .limit(10)
        .all()
    )
    top_categories = [
        {"category_id": cid, "category_name": name, "revenue": Decimal(rev or 0), "quantity_sold": qty}
        for cid, name, rev, qty in top_categories_rows
    ]

    # --- Payment method / channel breakdowns ---
    payment_rows = (
        db.query(Sale.payment_method, func.sum(Sale.total_amount), func.count(Sale.id))
        .filter(Sale.id.in_(_matching_sale_ids(db, company_id, *filt_args)))
        .group_by(Sale.payment_method)
        .all()
    )
    by_payment_method = [
        {"payment_method": pm.value, "revenue": Decimal(rev or 0), "orders": cnt} for pm, rev, cnt in payment_rows
    ]

    channel_rows = (
        db.query(Sale.sales_channel, func.sum(Sale.total_amount), func.count(Sale.id))
        .filter(Sale.id.in_(_matching_sale_ids(db, company_id, *filt_args)))
        .group_by(Sale.sales_channel)
        .all()
    )
    by_sales_channel = [
        {"sales_channel": ch.value, "revenue": Decimal(rev or 0), "orders": cnt} for ch, rev, cnt in channel_rows
    ]

    # --- Customer revenue analysis --- (grouping by (customer_id, customer_name)
    # keeps unlinked/walk-in sales bucketed by name, same as before, since SQL
    # treats two NULL customer_ids as equal for GROUP BY purposes.)
    customer_rows = (
        db.query(Sale.customer_id, Sale.customer_name, func.sum(Sale.total_amount), func.count(Sale.id))
        .filter(Sale.id.in_(_matching_sale_ids(db, company_id, *filt_args)))
        .group_by(Sale.customer_id, Sale.customer_name)
        .order_by(func.sum(Sale.total_amount).desc())
        .limit(10)
        .all()
    )
    customer_revenue = []
    for cust_id, cust_name, spend, orders in customer_rows:
        spend = Decimal(spend or 0)
        customer_revenue.append({
            "customer_id": cust_id, "customer_name": cust_name, "orders": orders,
            "total_spend": spend, "average_order_value": spend / orders if orders else Decimal("0"),
        })

    # --- Inventory breakdowns ---
    inv_cat_rows = (
        _inventory_base_query(db, company_id, category_id, product_id, brand)
        .join(Category, Category.id == Product.category_id, isouter=True)
        .with_entities(
            Product.category_id, func.coalesce(Category.name, "Uncategorized"),
            func.coalesce(func.sum(Inventory.current_stock), 0),
            func.coalesce(func.sum(Inventory.current_stock * Product.unit_price), 0),
        )
        .group_by(Product.category_id, Category.name)
        .all()
    )
    inventory_by_category = [
        {"category_id": cid, "category_name": name, "quantity": qty, "value": Decimal(val or 0)}
        for cid, name, qty, val in inv_cat_rows
    ]

    status_rows = (
        _inventory_base_query(db, company_id, category_id, product_id, brand)
        .with_entities(Inventory.stock_status, func.count(Inventory.id))
        .group_by(Inventory.stock_status)
        .all()
    )
    inventory_status_summary = [{"status": s.value, "count": c} for s, c in status_rows]

    low_rows = (
        _inventory_base_query(db, company_id, category_id, product_id, brand)
        .filter(Inventory.stock_status == StockStatus.LOW_STOCK)
        .with_entities(Product.id, Product.name, Product.sku, Inventory.available_stock, Inventory.reorder_level)
        .order_by(Inventory.available_stock.asc())
        .limit(10)
        .all()
    )
    top_low_stock = [
        {"product_id": pid, "product_name": name, "sku": sku, "available_stock": avail, "reorder_level": rl}
        for pid, name, sku, avail, rl in low_rows
    ]

    oos_rows = (
        _inventory_base_query(db, company_id, category_id, product_id, brand)
        .filter(Inventory.stock_status == StockStatus.OUT_OF_STOCK)
        .with_entities(Product.id, Product.name, Product.sku, Inventory.updated_at)
        .all()
    )
    out_of_stock = [
        {"product_id": pid, "product_name": name, "sku": sku, "updated_at": upd}
        for pid, name, sku, upd in oos_rows
    ]

    return AnalyticsSummary(
        kpis={
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "total_products_sold": total_products_sold,
            "average_order_value": average_order_value,
            "total_discount": total_discount,
            "total_tax": total_tax,
            "total_inventory_value": total_inventory_value,
            "low_stock_products": low_stock_products,
            "out_of_stock_products": out_of_stock_products,
            "total_categories": total_categories,
        },
        revenue_trend=revenue_trend,
        top_products=top_products,
        top_categories=top_categories,
        by_payment_method=by_payment_method,
        by_sales_channel=by_sales_channel,
        customer_revenue=customer_revenue,
        inventory_by_category=inventory_by_category,
        inventory_status_summary=inventory_status_summary,
        top_low_stock=top_low_stock,
        out_of_stock=out_of_stock,
        inventory_value_by_category=inventory_by_category,
    )


@router.get("/summary", response_model=AnalyticsSummary)
def analytics_summary(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_id: Optional[str] = None,
    product_id: Optional[str] = None,
    brand: Optional[str] = None,
    sales_channel: Optional[str] = None,
    payment_method: Optional[str] = None,
    customer_id: Optional[str] = None,
    granularity: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ANALYTICS_ROLES)),
):
    return _build_summary(
        db, company_id, date_from, date_to, category_id, product_id, brand,
        sales_channel, payment_method, granularity, customer_id,
    )


@router.post("/audit", status_code=status.HTTP_204_NO_CONTENT)
def analytics_audit_event(
    payload: AnalyticsAuditEvent,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ANALYTICS_ROLES)),
):
    allowed_actions = {"Dashboard Viewed", "Dashboard Filters Applied"}
    if payload.action not in allowed_actions:
        raise HTTPException(status_code=400, detail="Unsupported audit action")
    log_action(
        db, request, payload.action,
        company_id=company_id, user_id=current_user.id,
        details=payload.details,
    )
    db.commit()


@router.get("/export")
def export_analytics(
    format: str = Query(..., pattern="^(csv|pdf)$"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_id: Optional[str] = None,
    product_id: Optional[str] = None,
    brand: Optional[str] = None,
    sales_channel: Optional[str] = None,
    payment_method: Optional[str] = None,
    customer_id: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ANALYTICS_ROLES)),
):
    summary = _build_summary(
        db, company_id, date_from, date_to, category_id, product_id, brand,
        sales_channel, payment_method, "daily", customer_id,
    )

    log_action(
        db, request, "Report Exported",
        company_id=company_id, user_id=current_user.id,
        details=f"format={format}",
    )
    db.commit()

    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["KPI", "Value"])
        for key, value in summary.kpis.model_dump().items():
            writer.writerow([key, value])
        writer.writerow([])
        writer.writerow(["Top Products", "SKU", "Qty Sold", "Revenue"])
        for row in summary.top_products:
            writer.writerow([row.product_name, row.sku, row.quantity_sold, row.revenue])
        writer.writerow([])
        writer.writerow(["Revenue Trend (Period)", "Revenue", "Orders"])
        for row in summary.revenue_trend:
            writer.writerow([row.period, row.revenue, row.orders])
        writer.writerow([])
        writer.writerow(["Top Customers", "Orders", "Total Spend", "Avg Order Value"])
        for row in summary.customer_revenue:
            writer.writerow([row.customer_name, row.orders, row.total_spend, row.average_order_value])
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=analytics_report.csv"},
        )

    # PDF export
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="PDF export requires the 'reportlab' package. Run: pip install reportlab",
        )

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [Paragraph("RetailPulse Analytics Report", styles["Title"]), Spacer(1, 0.5 * cm)]

    kpi_data = [["KPI", "Value"]] + [[k.replace("_", " ").title(), str(v)] for k, v in summary.kpis.model_dump().items()]
    kpi_table = Table(kpi_data, colWidths=[8 * cm, 6 * cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    elements += [kpi_table, Spacer(1, 0.8 * cm), Paragraph("Top Products", styles["Heading2"])]

    top_data = [["Product", "SKU", "Qty Sold", "Revenue"]] + [
        [row.product_name, row.sku, str(row.quantity_sold), str(row.revenue)]
        for row in summary.top_products
    ]
    top_table = Table(top_data, colWidths=[6 * cm, 3 * cm, 3 * cm, 3 * cm])
    top_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elements.append(top_table)

    elements += [Spacer(1, 0.8 * cm), Paragraph("Top Customers", styles["Heading2"])]
    cust_data = [["Customer", "Orders", "Total Spend", "Avg Order Value"]] + [
        [row.customer_name, str(row.orders), str(row.total_spend), str(row.average_order_value)]
        for row in summary.customer_revenue
    ]
    cust_table = Table(cust_data, colWidths=[6 * cm, 3 * cm, 3 * cm, 3 * cm])
    cust_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elements.append(cust_table)

    doc.build(elements)
    pdf_buffer.seek(0)
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=analytics_report.pdf"},
    )
