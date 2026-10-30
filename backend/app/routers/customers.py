import csv
import io
from collections import defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, asc, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    Customer, CustomerPurchaseSummary, CustomerActivity, CustomerActivityType,
    CustomerType, CustomerStatus, CustomerSegment, Sale, SaleItem, User, UserRole,
)
from app.schemas import (
    CustomerCreate, CustomerUpdate, CustomerStatusUpdate,
    CustomerOut, CustomerListItem, CustomerListResponse,
    CustomerActivityOut, CustomerRecentSale, CustomerProfileOut,
    CustomerAnalyticsKPIs, CustomerGrowthPoint, NewVsReturningPoint, RevenueByTypeRow,
    TopCustomerRow, PurchaseFrequencyBucket, LocationRow, MonthlyAcquisitionPoint,
    SpendingDistributionBucket, SegmentBreakdown, CustomerAnalyticsSummary,
)
from app.dependencies import require_roles, get_current_company_id
from app.audit import log_action
from app.services.customers import (
    generate_customer_code, log_customer_activity, scan_inactive_customers,
)
from app.models.notifications import NotificationType, NotificationPriority
from app.services.notifications import notify_roles

router = APIRouter(prefix="/customers", tags=["customers"])

CUSTOMER_ROLES = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST]

SORT_FIELDS = {
    "name": Customer.full_name,
    "total_spend": CustomerPurchaseSummary.total_revenue,
    "total_orders": CustomerPurchaseSummary.total_orders,
    "last_purchase": CustomerPurchaseSummary.last_purchase_date,
    "customer_since": Customer.created_at,
}


def _get_customer_or_404(db: Session, company_id: str, customer_id: str) -> Customer:
    customer = db.query(Customer).options(
        joinedload(Customer.purchase_summary).joinedload(CustomerPurchaseSummary.favorite_product),
        joinedload(Customer.purchase_summary).joinedload(CustomerPurchaseSummary.favorite_category),
    ).filter(Customer.id == customer_id, Customer.company_id == company_id, Customer.is_deleted.is_(False)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


def _check_duplicate(db: Session, company_id: str, email: str, phone: str, exclude_id: Optional[str] = None):
    query = db.query(Customer).filter(
        Customer.company_id == company_id,
        Customer.is_deleted.is_(False),
        or_(Customer.email == email, Customer.phone == phone),
    )
    if exclude_id:
        query = query.filter(Customer.id != exclude_id)
    existing = query.first()
    if existing:
        field = "email" if existing.email == email else "phone"
        raise HTTPException(status_code=400, detail=f"A customer with this {field} already exists")


def _serialize_list_item(customer: Customer, summary: Optional[CustomerPurchaseSummary]) -> CustomerListItem:
    return CustomerListItem(
        id=customer.id,
        customer_code=customer.customer_code,
        full_name=customer.full_name,
        email=customer.email,
        phone=customer.phone,
        city=customer.city,
        state=customer.state,
        country=customer.country,
        customer_type=customer.customer_type,
        status=customer.status,
        segment=customer.segment,
        total_orders=summary.total_orders if summary else 0,
        total_revenue=summary.total_revenue if summary else Decimal("0"),
        last_purchase_date=summary.last_purchase_date if summary else None,
        created_at=customer.created_at,
    )


# ---------- List & Create ----------

@router.get("", response_model=CustomerListResponse)
def list_customers(
    search: Optional[str] = None,
    customer_type: Optional[CustomerType] = None,
    status_filter: Optional[CustomerStatus] = Query(None, alias="status"),
    city: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None,
    registered_from: Optional[date] = None,
    registered_to: Optional[date] = None,
    sort_by: str = Query("customer_since", pattern="^(name|total_spend|total_orders|last_purchase|customer_since)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(CUSTOMER_ROLES)),
):
    query = db.query(Customer, CustomerPurchaseSummary).outerjoin(
        CustomerPurchaseSummary, CustomerPurchaseSummary.customer_id == Customer.id
    ).filter(Customer.company_id == company_id, Customer.is_deleted.is_(False))

    if search:
        like = f"%{search}%"
        query = query.filter(or_(
            Customer.full_name.ilike(like),
            Customer.customer_code.ilike(like),
            Customer.email.ilike(like),
            Customer.phone.ilike(like),
        ))

    if customer_type:
        query = query.filter(Customer.customer_type == customer_type)
    if status_filter:
        query = query.filter(Customer.status == status_filter)
    if city:
        query = query.filter(Customer.city.ilike(f"%{city}%"))
    if state:
        query = query.filter(Customer.state.ilike(f"%{state}%"))
    if country:
        query = query.filter(Customer.country.ilike(f"%{country}%"))
    if registered_from:
        query = query.filter(Customer.created_at >= datetime.combine(registered_from, datetime.min.time()))
    if registered_to:
        query = query.filter(Customer.created_at <= datetime.combine(registered_to, datetime.max.time()))

    total = query.count()

    sort_column = SORT_FIELDS[sort_by]
    order_fn = asc if sort_dir == "asc" else desc
    query = query.order_by(order_fn(sort_column))

    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    return CustomerListResponse(items=[_serialize_list_item(c, s) for c, s in rows], total=total)


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(CUSTOMER_ROLES)),
):
    _check_duplicate(db, company_id, payload.email, payload.phone)

    customer = Customer(
        company_id=company_id,
        customer_code=generate_customer_code(db, company_id),
        first_name=payload.first_name,
        last_name=payload.last_name,
        full_name=f"{payload.first_name} {payload.last_name}".strip(),
        email=payload.email,
        phone=payload.phone,
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        address=payload.address,
        city=payload.city,
        state=payload.state,
        country=payload.country,
        postal_code=payload.postal_code,
        customer_type=payload.customer_type,
        preferred_channel=payload.preferred_channel,
        status=payload.status,
        created_by=current_user.id,
    )
    db.add(customer)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A customer with this email or phone already exists")

    db.add(CustomerPurchaseSummary(customer_id=customer.id, company_id=company_id))
    log_customer_activity(
        db, customer.id, company_id, CustomerActivityType.REGISTERED,
        f"Registered as a {payload.customer_type.value.title()} customer.",
    )
    notify_roles(
        db, company_id, NotificationType.CUSTOMER_REGISTERED,
        title="New Customer",
        message=f"New customer registered: {customer.full_name} ({customer.customer_code}).",
        priority=NotificationPriority.LOW,
        customer_id=customer.id, resource_type="Customer", resource_id=customer.id,
    )
    db.commit()
    db.refresh(customer)

    log_action(db, request, "Customer Created", company_id=company_id, user_id=current_user.id,
               entity_name=f"{customer.customer_code} ({customer.full_name})")
    db.commit()

    return _get_customer_or_404(db, company_id, customer.id)


# ---------- Export (must precede /{customer_id}) ----------

@router.get("/export")
def export_customers(
    format: str = Query(..., pattern="^(csv|pdf)$"),
    search: Optional[str] = None,
    customer_type: Optional[CustomerType] = None,
    status_filter: Optional[CustomerStatus] = Query(None, alias="status"),
    request: Request = None,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(CUSTOMER_ROLES)),
):
    query = db.query(Customer, CustomerPurchaseSummary).outerjoin(
        CustomerPurchaseSummary, CustomerPurchaseSummary.customer_id == Customer.id
    ).filter(Customer.company_id == company_id, Customer.is_deleted.is_(False))
    if search:
        like = f"%{search}%"
        query = query.filter(or_(Customer.full_name.ilike(like), Customer.customer_code.ilike(like)))
    if customer_type:
        query = query.filter(Customer.customer_type == customer_type)
    if status_filter:
        query = query.filter(Customer.status == status_filter)
    rows = query.order_by(Customer.full_name).all()

    log_action(db, request, "Customer Exported", company_id=company_id, user_id=current_user.id,
               details=f"format={format}, count={len(rows)}")
    db.commit()

    headers = ["Customer ID", "Name", "Email", "Phone", "Type", "Status", "Segment",
               "City", "State", "Country", "Total Orders", "Total Revenue", "Last Purchase", "Customer Since"]

    def row_values(c: Customer, s: Optional[CustomerPurchaseSummary]):
        return [
            c.customer_code, c.full_name, c.email, c.phone, c.customer_type.value, c.status.value,
            c.segment.value, c.city or "", c.state or "", c.country or "",
            s.total_orders if s else 0, str(s.total_revenue) if s else "0",
            s.last_purchase_date.strftime("%Y-%m-%d") if s and s.last_purchase_date else "",
            c.created_at.strftime("%Y-%m-%d"),
        ]

    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        for c, s in rows:
            writer.writerow(row_values(c, s))
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=customers.csv"},
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
    elements = [Paragraph("RetailPulse Customer List", styles["Title"]), Spacer(1, 0.5 * cm)]

    data = [headers] + [row_values(c, s) for c, s in rows]
    table = Table(data, repeatRows=1)
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
        headers={"Content-Disposition": "attachment; filename=customers.pdf"},
    )


# ---------- Analytics ----------

def _month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


@router.get("/analytics/summary", response_model=CustomerAnalyticsSummary)
def get_customer_analytics_summary(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(CUSTOMER_ROLES)),
):
    scan_inactive_customers(db, company_id)

    customers = db.query(Customer).filter(Customer.company_id == company_id, Customer.is_deleted.is_(False)).all()
    summaries = {
        s.customer_id: s for s in db.query(CustomerPurchaseSummary).filter(
            CustomerPurchaseSummary.company_id == company_id
        ).all()
    }

    total_customers = len(customers)
    active_customers = sum(1 for c in customers if c.status == CustomerStatus.ACTIVE)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    new_customers = sum(1 for c in customers if c.created_at >= thirty_days_ago)

    with_orders = [s for s in summaries.values() if s.total_orders > 0]
    returning_customers = sum(1 for s in with_orders if s.total_orders >= 2)
    total_revenue_generated = sum((s.total_revenue for s in summaries.values()), Decimal("0"))
    average_customer_spend = (
        sum((s.total_revenue for s in with_orders), Decimal("0")) / len(with_orders)
        if with_orders else Decimal("0")
    )
    average_purchase_frequency = (
        Decimal(sum(s.total_orders for s in with_orders)) / len(with_orders)
        if with_orders else Decimal("0")
    )

    kpis = CustomerAnalyticsKPIs(
        total_customers=total_customers,
        active_customers=active_customers,
        new_customers=new_customers,
        returning_customers=returning_customers,
        average_customer_spend=average_customer_spend,
        total_revenue_generated=total_revenue_generated,
        average_purchase_frequency=average_purchase_frequency,
    )

    # ---- Growth trend & monthly acquisition (last 12 months) ----
    months = []
    cursor = datetime.utcnow().replace(day=1)
    for i in range(11, -1, -1):
        year = cursor.year
        month = cursor.month - i
        while month <= 0:
            month += 12
            year -= 1
        months.append(f"{year:04d}-{month:02d}")

    new_by_month = defaultdict(int)
    for c in customers:
        key = _month_key(c.created_at)
        if key in months:
            new_by_month[key] += 1

    growth_trend = []
    running_total = total_customers - sum(new_by_month.values())
    running_total = max(running_total, 0)
    for m in months:
        running_total += new_by_month[m]
        growth_trend.append(CustomerGrowthPoint(period=m, new_customers=new_by_month[m], total_customers=running_total))

    monthly_acquisition = [MonthlyAcquisitionPoint(period=m, new_customers=new_by_month[m]) for m in months]

    # ---- New vs returning (last 6 months, based on sales activity) ----
    six_months_ago = datetime.utcnow() - timedelta(days=182)
    sales_rows = db.query(Sale.customer_id, Sale.sale_date).filter(
        Sale.company_id == company_id, Sale.customer_id.isnot(None), Sale.sale_date >= six_months_ago,
    ).all()
    first_purchase_by_customer = {cid: s.first_purchase_date for cid, s in summaries.items() if s.first_purchase_date}

    nvr = defaultdict(lambda: {"new": set(), "returning": set()})
    for cid, sale_date in sales_rows:
        key = _month_key(sale_date)
        first = first_purchase_by_customer.get(cid)
        if first and _month_key(first) == key:
            nvr[key]["new"].add(cid)
        else:
            nvr[key]["returning"].add(cid)

    new_vs_returning = [
        NewVsReturningPoint(period=m, new_customers=len(nvr[m]["new"]), returning_customers=len(nvr[m]["returning"]))
        for m in months[-6:]
    ]

    # ---- Revenue by customer type ----
    by_type = defaultdict(lambda: {"revenue": Decimal("0"), "count": 0})
    for c in customers:
        s = summaries.get(c.id)
        by_type[c.customer_type]["revenue"] += s.total_revenue if s else Decimal("0")
        by_type[c.customer_type]["count"] += 1
    revenue_by_type = [
        RevenueByTypeRow(customer_type=t, revenue=v["revenue"], customer_count=v["count"])
        for t, v in by_type.items()
    ]

    # ---- Top 10 customers by revenue ----
    ranked = sorted(customers, key=lambda c: summaries.get(c.id).total_revenue if summaries.get(c.id) else Decimal("0"), reverse=True)
    top_customers = [
        TopCustomerRow(
            customer_id=c.id, customer_code=c.customer_code, full_name=c.full_name,
            revenue=summaries[c.id].total_revenue if c.id in summaries else Decimal("0"),
            total_orders=summaries[c.id].total_orders if c.id in summaries else 0,
        )
        for c in ranked[:10] if c.id in summaries and summaries[c.id].total_orders > 0
    ]

    # ---- Purchase frequency buckets ----
    freq_buckets = {"0": 0, "1": 0, "2-4": 0, "5-9": 0, "10+": 0}
    for s in summaries.values():
        o = s.total_orders
        if o == 0:
            freq_buckets["0"] += 1
        elif o == 1:
            freq_buckets["1"] += 1
        elif o <= 4:
            freq_buckets["2-4"] += 1
        elif o <= 9:
            freq_buckets["5-9"] += 1
        else:
            freq_buckets["10+"] += 1
    purchase_frequency = [PurchaseFrequencyBucket(bucket=k, customer_count=v) for k, v in freq_buckets.items()]

    # ---- Location distribution (top 10 by city) ----
    loc_counts = defaultdict(int)
    for c in customers:
        label = c.city or "Unknown"
        loc_counts[label] += 1
    location_distribution = [
        LocationRow(location=k, customer_count=v)
        for k, v in sorted(loc_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    ]

    # ---- Spending distribution ----
    spend_buckets = {"₹0": 0, "₹1–5K": 0, "₹5K–25K": 0, "₹25K–100K": 0, "₹100K+": 0}
    for s in summaries.values():
        r = s.total_revenue
        if r <= 0:
            spend_buckets["₹0"] += 1
        elif r <= 5000:
            spend_buckets["₹1–5K"] += 1
        elif r <= 25000:
            spend_buckets["₹5K–25K"] += 1
        elif r <= 100000:
            spend_buckets["₹25K–100K"] += 1
        else:
            spend_buckets["₹100K+"] += 1
    spending_distribution = [SpendingDistributionBucket(bucket=k, customer_count=v) for k, v in spend_buckets.items()]

    # ---- Segment breakdown ----
    seg_counts = defaultdict(int)
    for c in customers:
        seg_counts[c.segment] += 1
    segment_breakdown = [SegmentBreakdown(segment=s, customer_count=seg_counts.get(s, 0)) for s in CustomerSegment]

    return CustomerAnalyticsSummary(
        kpis=kpis,
        growth_trend=growth_trend,
        new_vs_returning=new_vs_returning,
        revenue_by_type=revenue_by_type,
        top_customers=top_customers,
        purchase_frequency=purchase_frequency,
        location_distribution=location_distribution,
        monthly_acquisition=monthly_acquisition,
        spending_distribution=spending_distribution,
        segment_breakdown=segment_breakdown,
    )


@router.get("/analytics/export")
def export_customer_analytics(
    format: str = Query(..., pattern="^(csv|pdf)$"),
    request: Request = None,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(CUSTOMER_ROLES)),
):
    summary = get_customer_analytics_summary(db=db, company_id=company_id, current_user=current_user)

    log_action(db, request, "Customer Exported", company_id=company_id, user_id=current_user.id,
               details=f"format={format}, report=customer_analytics")
    db.commit()

    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["KPI", "Value"])
        for key, value in summary.kpis.model_dump().items():
            writer.writerow([key, value])
        writer.writerow([])
        writer.writerow(["Top Customers", "Code", "Revenue", "Orders"])
        for row in summary.top_customers:
            writer.writerow([row.full_name, row.customer_code, row.revenue, row.total_orders])
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=customer_analytics.csv"},
        )

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF export requires the 'reportlab' package.")

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [Paragraph("RetailPulse Customer Analytics Report", styles["Title"]), Spacer(1, 0.5 * cm)]

    kpi_data = [["KPI", "Value"]] + [[k.replace("_", " ").title(), str(v)] for k, v in summary.kpis.model_dump().items()]
    kpi_table = Table(kpi_data, colWidths=[8 * cm, 6 * cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    elements += [kpi_table, Spacer(1, 0.8 * cm), Paragraph("Top Customers", styles["Heading2"])]

    top_data = [["Customer", "Code", "Revenue", "Orders"]] + [
        [row.full_name, row.customer_code, str(row.revenue), str(row.total_orders)] for row in summary.top_customers
    ]
    top_table = Table(top_data, colWidths=[6 * cm, 4 * cm, 4 * cm, 3 * cm])
    top_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elements.append(top_table)

    doc.build(elements)
    pdf_buffer.seek(0)
    return StreamingResponse(
        pdf_buffer, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=customer_analytics.pdf"},
    )


@router.get("/analytics/top-customers/export")
def export_top_customers(
    format: str = Query(..., pattern="^(csv|pdf)$"),
    limit: int = Query(10, ge=1, le=100),
    request: Request = None,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(CUSTOMER_ROLES)),
):
    rows = db.query(Customer, CustomerPurchaseSummary).join(
        CustomerPurchaseSummary, CustomerPurchaseSummary.customer_id == Customer.id
    ).filter(
        Customer.company_id == company_id, Customer.is_deleted.is_(False), CustomerPurchaseSummary.total_orders > 0
    ).order_by(CustomerPurchaseSummary.total_revenue.desc()).limit(limit).all()

    log_action(db, request, "Customer Exported", company_id=company_id, user_id=current_user.id,
               details=f"format={format}, report=top_customers")
    db.commit()

    headers = ["Rank", "Customer Code", "Name", "Total Orders", "Total Revenue", "Avg Order Value"]

    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        for idx, (c, s) in enumerate(rows, start=1):
            writer.writerow([idx, c.customer_code, c.full_name, s.total_orders, s.total_revenue, s.average_order_value])
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=top_customers.csv"},
        )

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF export requires the 'reportlab' package.")

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [Paragraph("RetailPulse Top Customers Report", styles["Title"]), Spacer(1, 0.5 * cm)]
    data = [headers] + [
        [idx, c.customer_code, c.full_name, s.total_orders, str(s.total_revenue), str(s.average_order_value)]
        for idx, (c, s) in enumerate(rows, start=1)
    ]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elements.append(table)
    doc.build(elements)
    pdf_buffer.seek(0)
    return StreamingResponse(
        pdf_buffer, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=top_customers.pdf"},
    )


# ---------- Detail / Update / Delete ----------

@router.get("/{customer_id}", response_model=CustomerProfileOut)
def get_customer_profile(
    customer_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(CUSTOMER_ROLES)),
):
    customer = _get_customer_or_404(db, company_id, customer_id)

    activities = db.query(CustomerActivity).filter(
        CustomerActivity.customer_id == customer_id
    ).order_by(CustomerActivity.created_at.desc()).limit(15).all()

    sales = db.query(Sale).options(joinedload(Sale.items)).filter(
        Sale.customer_id == customer_id, Sale.company_id == company_id
    ).order_by(Sale.sale_date.desc()).limit(5).all()

    recent_transactions = [
        CustomerRecentSale(
            id=s.id, invoice_number=s.invoice_number, sale_date=s.sale_date,
            total_amount=s.total_amount, item_count=len(s.items),
        )
        for s in sales
    ]

    return CustomerProfileOut(
        customer=CustomerOut.model_validate(customer),
        recent_activities=[CustomerActivityOut.model_validate(a) for a in activities],
        recent_transactions=recent_transactions,
    )


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: str,
    payload: CustomerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(CUSTOMER_ROLES)),
):
    customer = _get_customer_or_404(db, company_id, customer_id)

    new_email = payload.email if payload.email is not None else customer.email
    new_phone = payload.phone if payload.phone is not None else customer.phone
    if new_email != customer.email or new_phone != customer.phone:
        _check_duplicate(db, company_id, new_email, new_phone, exclude_id=customer_id)

    changed_fields = []
    before_snapshot = {}
    after_snapshot = {}
    for field in ["first_name", "last_name", "email", "phone", "date_of_birth", "gender", "address",
                  "city", "state", "country", "postal_code", "customer_type", "preferred_channel"]:
        value = getattr(payload, field)
        if value is not None and getattr(customer, field) != value:
            before_snapshot[field] = getattr(customer, field)
            setattr(customer, field, value)
            after_snapshot[field] = value
            changed_fields.append(field)

    if "first_name" in changed_fields or "last_name" in changed_fields:
        customer.full_name = f"{customer.first_name} {customer.last_name}".strip()

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A customer with this email or phone already exists")

    if changed_fields:
        log_customer_activity(
            db, customer.id, company_id, CustomerActivityType.PROFILE_UPDATED,
            f"Profile updated: {', '.join(changed_fields)}.",
        )

    db.commit()
    db.refresh(customer)

    log_action(db, request, "Customer Updated", company_id=company_id, user_id=current_user.id,
               entity_name=f"{customer.customer_code} ({customer.full_name})",
               resource_type="Customer", resource_id=customer.id,
               before=before_snapshot or None, after=after_snapshot or None)
    db.commit()

    return _get_customer_or_404(db, company_id, customer.id)


@router.patch("/{customer_id}/status", response_model=CustomerOut)
def update_customer_status(
    customer_id: str,
    payload: CustomerStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(CUSTOMER_ROLES)),
):
    customer = _get_customer_or_404(db, company_id, customer_id)

    if customer.status == payload.status:
        return customer

    customer.status = payload.status
    if payload.status == CustomerStatus.INACTIVE:
        customer.deactivated_at = datetime.utcnow()
        log_customer_activity(db, customer.id, company_id, CustomerActivityType.DEACTIVATED, "Customer deactivated.")
        audit_action = "Customer Deactivated"
    else:
        customer.deactivated_at = None
        log_customer_activity(db, customer.id, company_id, CustomerActivityType.REACTIVATED, "Customer reactivated.")
        audit_action = "Customer Activated"

    db.commit()
    db.refresh(customer)

    log_action(db, request, audit_action, company_id=company_id, user_id=current_user.id,
               entity_name=f"{customer.customer_code} ({customer.full_name})")
    db.commit()

    return _get_customer_or_404(db, company_id, customer.id)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: str,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(CUSTOMER_ROLES)),
):
    customer = _get_customer_or_404(db, company_id, customer_id)
    label = f"{customer.customer_code} ({customer.full_name})"

    customer.is_deleted = True
    customer.deleted_at = datetime.utcnow()
    db.commit()

    log_action(db, request, "Customer Deleted", company_id=company_id, user_id=current_user.id, entity_name=label)
    db.commit()
    return None


@router.get("/{customer_id}/timeline", response_model=list[CustomerActivityOut])
def get_customer_timeline(
    customer_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(CUSTOMER_ROLES)),
):
    _get_customer_or_404(db, company_id, customer_id)
    return db.query(CustomerActivity).filter(
        CustomerActivity.customer_id == customer_id
    ).order_by(CustomerActivity.created_at.desc()).limit(100).all()


@router.get("/{customer_id}/purchases")
def get_customer_purchases(
    customer_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(CUSTOMER_ROLES)),
):
    _get_customer_or_404(db, company_id, customer_id)

    query = db.query(Sale).options(joinedload(Sale.items)).filter(
        Sale.customer_id == customer_id, Sale.company_id == company_id
    ).order_by(Sale.sale_date.desc())

    total = query.count()
    sales = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        CustomerRecentSale(
            id=s.id, invoice_number=s.invoice_number, sale_date=s.sale_date,
            total_amount=s.total_amount, item_count=len(s.items),
        )
        for s in sales
    ]
    return {"items": items, "total": total}
