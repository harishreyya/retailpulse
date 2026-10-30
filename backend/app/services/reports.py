"""
Task 15: Reporting & Scheduled Reports — report generation.

Deliberately does NOT duplicate business data anywhere: every report type
below is a read-only SQL query over the existing Sales/Inventory/
Customer/Product tables, the same ones Analytics/Inventory
Forecast/Customer Analytics already read from. A `Report` row records
that a generation happened (for History) and optionally snapshots the
rendered export file; it never becomes a second copy of the underlying
business data.

Each report function takes the same shape of arguments and returns the
same shape of result — (columns, rows, total, period_start, period_end)
— so the router and the scheduler can treat all 5 report types
identically instead of special-casing each one.
"""
import csv
import io
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, case, or_
from sqlalchemy.orm import Session

from app.models import (
    ReportType, Sale, SaleItem, Product, Category, Customer, CustomerPurchaseSummary,
    Inventory, InventoryMovement, PaymentStatus, StockStatus, MovementType,
)
from app.schemas.reports import ReportFilters, ReportColumn

PDF_ROW_LIMIT = 2_000  # see services/audit_logs.py for the same reasoning


def _dt_bounds(filters: ReportFilters) -> tuple[Optional[datetime], Optional[datetime]]:
    start = datetime.combine(filters.date_from, time.min) if filters.date_from else None
    end = datetime.combine(filters.date_to, time.max) if filters.date_to else None
    return start, end


# ============================================================= SALES

SALES_COLUMNS = [
    ReportColumn(key="invoice_number", label="Invoice #"),
    ReportColumn(key="sale_date", label="Date"),
    ReportColumn(key="customer_name", label="Customer"),
    ReportColumn(key="sales_channel", label="Channel"),
    ReportColumn(key="payment_method", label="Payment Method"),
    ReportColumn(key="payment_status", label="Status"),
    ReportColumn(key="items_count", label="Items"),
    ReportColumn(key="total_amount", label="Total"),
]


def _sales_report(db: Session, company_id: str, filters: ReportFilters, sort_by: Optional[str], sort_dir: str):
    start, end = _dt_bounds(filters)
    query = db.query(
        Sale.id, Sale.invoice_number, Sale.sale_date, Sale.customer_name, Sale.customer_id,
        Sale.sales_channel, Sale.payment_method, Sale.payment_status, Sale.total_amount,
        func.count(SaleItem.id).label("items_count"),
    ).join(SaleItem, SaleItem.sale_id == Sale.id).filter(Sale.company_id == company_id)

    if start:
        query = query.filter(Sale.sale_date >= start)
    if end:
        query = query.filter(Sale.sale_date <= end)
    if filters.customer_id:
        query = query.filter(Sale.customer_id == filters.customer_id)
    if filters.sales_status:
        query = query.filter(Sale.payment_status == filters.sales_status)
    if filters.product_id or filters.category_id or filters.brand:
        query = query.join(Product, Product.id == SaleItem.product_id)
        if filters.product_id:
            query = query.filter(SaleItem.product_id == filters.product_id)
        if filters.category_id:
            query = query.filter(SaleItem.category_id == filters.category_id)
        if filters.brand:
            query = query.filter(Product.brand == filters.brand)
    if filters.search:
        like = f"%{filters.search}%"
        query = query.filter(or_(Sale.invoice_number.ilike(like), Sale.customer_name.ilike(like)))

    query = query.group_by(Sale.id)

    sort_map = {"date": Sale.sale_date, "total": Sale.total_amount, "customer": Sale.customer_name}
    sort_col = sort_map.get(sort_by, Sale.sale_date)
    query = query.order_by(sort_col.asc() if sort_dir == "asc" else sort_col.desc())

    return query, start, end


def _serialize_sales_row(r) -> dict:
    return {
        "invoice_number": r.invoice_number, "sale_date": r.sale_date.isoformat(),
        "customer_name": r.customer_name, "sales_channel": r.sales_channel.value,
        "payment_method": r.payment_method.value, "payment_status": r.payment_status.value,
        "items_count": r.items_count, "total_amount": str(r.total_amount),
    }


# ============================================================= INVENTORY

INVENTORY_COLUMNS = [
    ReportColumn(key="product_name", label="Product"),
    ReportColumn(key="sku", label="SKU"),
    ReportColumn(key="category_name", label="Category"),
    ReportColumn(key="brand", label="Brand"),
    ReportColumn(key="current_stock", label="Current Stock"),
    ReportColumn(key="reorder_level", label="Reorder Level"),
    ReportColumn(key="stock_status", label="Status"),
    ReportColumn(key="stock_value", label="Stock Value"),
]


def _inventory_report(db: Session, company_id: str, filters: ReportFilters, sort_by: Optional[str], sort_dir: str):
    query = db.query(
        Product.id, Product.name, Product.sku, Product.brand, Category.name.label("category_name"),
        Inventory.current_stock, Inventory.reorder_level, Inventory.stock_status, Product.unit_price,
    ).join(Inventory, Inventory.product_id == Product.id).join(Category, Category.id == Product.category_id).filter(
        Inventory.company_id == company_id
    )

    if filters.category_id:
        query = query.filter(Product.category_id == filters.category_id)
    if filters.brand:
        query = query.filter(Product.brand == filters.brand)
    if filters.product_id:
        query = query.filter(Product.id == filters.product_id)
    if filters.stock_status:
        query = query.filter(Inventory.stock_status == filters.stock_status)
    if filters.search:
        like = f"%{filters.search}%"
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))

    sort_map = {
        "stock": Inventory.current_stock, "name": Product.name,
        "value": (Inventory.current_stock * Product.unit_price),
    }
    sort_col = sort_map.get(sort_by, Product.name)
    query = query.order_by(sort_col.asc() if sort_dir == "asc" else sort_col.desc())

    return query, None, None


def _serialize_inventory_row(r) -> dict:
    return {
        "product_name": r.name, "sku": r.sku, "category_name": r.category_name, "brand": r.brand or "",
        "current_stock": r.current_stock, "reorder_level": r.reorder_level,
        "stock_status": r.stock_status.value, "stock_value": str(Decimal(r.current_stock) * r.unit_price),
    }


# ============================================================= CUSTOMER

CUSTOMER_COLUMNS = [
    ReportColumn(key="customer_code", label="Customer Code"),
    ReportColumn(key="full_name", label="Name"),
    ReportColumn(key="email", label="Email"),
    ReportColumn(key="customer_type", label="Type"),
    ReportColumn(key="total_orders", label="Orders"),
    ReportColumn(key="total_revenue", label="Total Spend"),
    ReportColumn(key="last_purchase_date", label="Last Purchase"),
]


def _customer_report(db: Session, company_id: str, filters: ReportFilters, sort_by: Optional[str], sort_dir: str):
    query = db.query(
        Customer.id, Customer.customer_code, Customer.full_name, Customer.email, Customer.customer_type,
        func.coalesce(CustomerPurchaseSummary.total_orders, 0).label("total_orders"),
        func.coalesce(CustomerPurchaseSummary.total_revenue, 0).label("total_revenue"),
        CustomerPurchaseSummary.last_purchase_date,
    ).outerjoin(CustomerPurchaseSummary, CustomerPurchaseSummary.customer_id == Customer.id).filter(
        Customer.company_id == company_id, Customer.is_deleted.is_(False)
    )

    if filters.customer_id:
        query = query.filter(Customer.id == filters.customer_id)
    if filters.date_from:
        query = query.filter(CustomerPurchaseSummary.last_purchase_date >= datetime.combine(filters.date_from, time.min))
    if filters.date_to:
        query = query.filter(CustomerPurchaseSummary.last_purchase_date <= datetime.combine(filters.date_to, time.max))
    if filters.search:
        like = f"%{filters.search}%"
        query = query.filter(or_(Customer.full_name.ilike(like), Customer.email.ilike(like), Customer.customer_code.ilike(like)))

    sort_map = {
        "revenue": CustomerPurchaseSummary.total_revenue, "orders": CustomerPurchaseSummary.total_orders,
        "name": Customer.full_name,
    }
    sort_col = sort_map.get(sort_by, CustomerPurchaseSummary.total_revenue)
    query = query.order_by(sort_col.asc().nullslast() if sort_dir == "asc" else sort_col.desc().nullslast())

    return query, None, None


def _serialize_customer_row(r) -> dict:
    return {
        "customer_code": r.customer_code, "full_name": r.full_name, "email": r.email,
        "customer_type": r.customer_type.value, "total_orders": r.total_orders,
        "total_revenue": str(r.total_revenue), "last_purchase_date": r.last_purchase_date.isoformat() if r.last_purchase_date else "",
    }


# ============================================================= PRODUCT PERFORMANCE

PRODUCT_PERFORMANCE_COLUMNS = [
    ReportColumn(key="product_name", label="Product"),
    ReportColumn(key="sku", label="SKU"),
    ReportColumn(key="category_name", label="Category"),
    ReportColumn(key="quantity_sold", label="Qty Sold"),
    ReportColumn(key="revenue", label="Revenue"),
    ReportColumn(key="orders_count", label="Orders"),
    ReportColumn(key="current_stock", label="Current Stock"),
]


def _product_performance_report(db: Session, company_id: str, filters: ReportFilters, sort_by: Optional[str], sort_dir: str):
    start, end = _dt_bounds(filters)
    quantity_sold_expr = func.coalesce(func.sum(SaleItem.quantity), 0)
    revenue_expr = func.coalesce(func.sum(SaleItem.total), 0)

    query = db.query(
        Product.id, Product.name, Product.sku, Category.name.label("category_name"),
        quantity_sold_expr.label("quantity_sold"),
        revenue_expr.label("revenue"),
        func.count(func.distinct(SaleItem.sale_id)).label("orders_count"),
    ).join(Category, Category.id == Product.category_id).outerjoin(
        SaleItem, SaleItem.product_id == Product.id
    ).outerjoin(Sale, Sale.id == SaleItem.sale_id).filter(Product.company_id == company_id)

    if start:
        query = query.filter(or_(Sale.sale_date >= start, Sale.id.is_(None)))
    if end:
        query = query.filter(or_(Sale.sale_date <= end, Sale.id.is_(None)))
    if filters.category_id:
        query = query.filter(Product.category_id == filters.category_id)
    if filters.brand:
        query = query.filter(Product.brand == filters.brand)
    if filters.product_id:
        query = query.filter(Product.id == filters.product_id)

    query = query.group_by(Product.id, Category.name)

    # Sort by the same aggregate expression used in SELECT above — ordering
    # by a column alias string is dialect-dependent, so the expression
    # itself (not its label) is what's passed to order_by here.
    sort_map = {"revenue": revenue_expr, "quantity": quantity_sold_expr}
    sort_expr = sort_map.get(sort_by, revenue_expr)
    query = query.order_by(sort_expr.asc() if sort_dir == "asc" else sort_expr.desc())

    # Joined separately for current_stock — not part of the sales
    # aggregate, and a product with zero sales still needs a stock figure.
    inv_by_product = {
        inv.product_id: inv.current_stock
        for inv in db.query(Inventory).filter(Inventory.company_id == company_id).all()
    }
    return query, start, end, inv_by_product


def _serialize_product_performance_row(r, inv_by_product: dict) -> dict:
    return {
        "product_name": r.name, "sku": r.sku, "category_name": r.category_name,
        "quantity_sold": r.quantity_sold, "revenue": str(r.revenue), "orders_count": r.orders_count,
        "current_stock": inv_by_product.get(r.id, 0),
    }


# ============================================================= STOCK MOVEMENT

STOCK_MOVEMENT_COLUMNS = [
    ReportColumn(key="created_at", label="Date"),
    ReportColumn(key="product_name", label="Product"),
    ReportColumn(key="sku", label="SKU"),
    ReportColumn(key="movement_type", label="Type"),
    ReportColumn(key="quantity_changed", label="Change"),
    ReportColumn(key="previous_quantity", label="Before"),
    ReportColumn(key="updated_quantity", label="After"),
    ReportColumn(key="reason", label="Reason"),
    ReportColumn(key="performed_by_name", label="Performed By"),
]


def _stock_movement_report(db: Session, company_id: str, filters: ReportFilters, sort_by: Optional[str], sort_dir: str):
    from app.models import User
    start, end = _dt_bounds(filters)
    query = db.query(
        InventoryMovement.id, InventoryMovement.created_at, InventoryMovement.movement_type,
        InventoryMovement.quantity_changed, InventoryMovement.previous_quantity, InventoryMovement.updated_quantity,
        InventoryMovement.reason, Product.name, Product.sku, User.name.label("performed_by_name"),
    ).join(Inventory, Inventory.id == InventoryMovement.inventory_id).join(
        Product, Product.id == Inventory.product_id
    ).outerjoin(User, User.id == InventoryMovement.performed_by).filter(Inventory.company_id == company_id)

    if start:
        query = query.filter(InventoryMovement.created_at >= start)
    if end:
        query = query.filter(InventoryMovement.created_at <= end)
    if filters.product_id:
        query = query.filter(Product.id == filters.product_id)
    if filters.category_id:
        query = query.filter(Product.category_id == filters.category_id)
    if filters.movement_type:
        query = query.filter(InventoryMovement.movement_type == filters.movement_type)

    sort_col = InventoryMovement.created_at
    query = query.order_by(sort_col.asc() if sort_dir == "asc" else sort_col.desc())

    return query, start, end


def _serialize_stock_movement_row(r) -> dict:
    return {
        "created_at": r.created_at.isoformat(), "product_name": r.name, "sku": r.sku,
        "movement_type": r.movement_type.value, "quantity_changed": r.quantity_changed,
        "previous_quantity": r.previous_quantity, "updated_quantity": r.updated_quantity,
        "reason": r.reason, "performed_by_name": r.performed_by_name or "System",
    }


# ============================================================= Dispatch

REPORT_COLUMNS: dict[ReportType, list[ReportColumn]] = {
    ReportType.SALES: SALES_COLUMNS,
    ReportType.INVENTORY: INVENTORY_COLUMNS,
    ReportType.CUSTOMER: CUSTOMER_COLUMNS,
    ReportType.PRODUCT_PERFORMANCE: PRODUCT_PERFORMANCE_COLUMNS,
    ReportType.STOCK_MOVEMENT: STOCK_MOVEMENT_COLUMNS,
}

REPORT_NAMES: dict[ReportType, str] = {
    ReportType.SALES: "Sales Report",
    ReportType.INVENTORY: "Inventory Report",
    ReportType.CUSTOMER: "Customer Report",
    ReportType.PRODUCT_PERFORMANCE: "Product Performance Report",
    ReportType.STOCK_MOVEMENT: "Stock Movement Report",
}


def run_report(
    db: Session, company_id: str, report_type: ReportType, filters: ReportFilters,
    sort_by: Optional[str] = None, sort_dir: str = "desc",
    page: int = 1, page_size: int = 50,
) -> dict:
    """
    Runs the query for `report_type`, paginates it, and returns a plain
    dict shape shared by every report type:
        {columns, rows, total, period_start, period_end}
    `rows` are plain JSON-safe dicts (Decimals/enums/datetimes already
    stringified) so this can go straight into an API response or a CSV
    writer with no further transformation.
    """
    if report_type == ReportType.SALES:
        query, start, end = _sales_report(db, company_id, filters, sort_by, sort_dir)
        total = query.count()
        rows = [_serialize_sales_row(r) for r in query.offset((page - 1) * page_size).limit(page_size).all()]
    elif report_type == ReportType.INVENTORY:
        query, start, end = _inventory_report(db, company_id, filters, sort_by, sort_dir)
        total = query.count()
        rows = [_serialize_inventory_row(r) for r in query.offset((page - 1) * page_size).limit(page_size).all()]
    elif report_type == ReportType.CUSTOMER:
        query, start, end = _customer_report(db, company_id, filters, sort_by, sort_dir)
        total = query.count()
        rows = [_serialize_customer_row(r) for r in query.offset((page - 1) * page_size).limit(page_size).all()]
    elif report_type == ReportType.PRODUCT_PERFORMANCE:
        query, start, end, inv_by_product = _product_performance_report(db, company_id, filters, sort_by, sort_dir)
        total = query.count()
        rows = [
            _serialize_product_performance_row(r, inv_by_product)
            for r in query.offset((page - 1) * page_size).limit(page_size).all()
        ]
    elif report_type == ReportType.STOCK_MOVEMENT:
        query, start, end = _stock_movement_report(db, company_id, filters, sort_by, sort_dir)
        total = query.count()
        rows = [_serialize_stock_movement_row(r) for r in query.offset((page - 1) * page_size).limit(page_size).all()]
    else:
        raise ValueError(f"Unknown report type: {report_type}")

    return {
        "columns": REPORT_COLUMNS[report_type], "rows": rows, "total": total,
        "period_start": start, "period_end": end,
    }


def run_report_all_rows(db: Session, company_id: str, report_type: ReportType, filters: ReportFilters, row_cap: int) -> dict:
    """Same as run_report but returns up to row_cap rows unpaginated, for export."""
    result = run_report(db, company_id, report_type, filters, page=1, page_size=row_cap)
    return result


# ============================================================= Export rendering

def render_csv(columns: list[ReportColumn], rows: list[dict], filters: ReportFilters) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([f"Filters: {_describe_filters(filters)}"])
    writer.writerow([])
    writer.writerow([c.label for c in columns])
    for row in rows:
        writer.writerow([row.get(c.key, "") for c in columns])
    return buffer.getvalue()


def render_pdf(title: str, columns: list[ReportColumn], rows: list[dict], filters: ReportFilters) -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(f"RetailPulse — {title}", styles["Title"]),
        Paragraph(_describe_filters(filters), styles["Normal"]),
        Spacer(1, 0.5 * cm),
    ]
    data = [[c.label for c in columns]] + [[str(row.get(c.key, "")) for c in columns] for row in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]))
    elements.append(table)
    doc.build(elements)
    buf.seek(0)
    return buf.read()


def _describe_filters(filters: ReportFilters) -> str:
    parts = []
    if filters.date_from or filters.date_to:
        parts.append(f"Period: {filters.date_from or 'earliest'} to {filters.date_to or 'latest'}")
    if filters.category_id:
        parts.append("Category filter applied")
    if filters.brand:
        parts.append(f"Brand: {filters.brand}")
    if filters.customer_id:
        parts.append("Customer filter applied")
    if filters.sales_status:
        parts.append(f"Sales status: {filters.sales_status}")
    if filters.stock_status:
        parts.append(f"Stock status: {filters.stock_status}")
    if filters.movement_type:
        parts.append(f"Movement type: {filters.movement_type}")
    if filters.search:
        parts.append(f"Search: '{filters.search}'")
    return "; ".join(parts) if parts else "No filters applied (all data)"
