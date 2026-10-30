from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Customer, CustomerPurchaseSummary, CustomerActivity, CustomerActivityType,
    CustomerSegment, CustomerStatus, Sale, SaleItem, Notification, NotificationType, NotificationPriority,
)
from app.services.notifications import notify_roles

# ---------- Segmentation thresholds ----------
# Tunable business rules for the four-tier segmentation model. A customer's
# segment is derived purely from total_orders / total_revenue on their
# purchase summary — no manual override exists yet.
VIP_MIN_REVENUE = Decimal("100000")
VIP_MIN_ORDERS = 8
LOYAL_MIN_REVENUE = Decimal("25000")
LOYAL_MIN_ORDERS = 4
REGULAR_MIN_ORDERS = 2

# A customer with no purchase in this many days (and at least one purchase
# on record) is flagged inactive by the inactivity scan.
INACTIVITY_DAYS = 90
# Don't re-notify about the same inactive customer more than once in this window.
INACTIVITY_RENOTIFY_DAYS = 30

LARGE_PURCHASE_THRESHOLD = Decimal("10000")


def generate_customer_code(db: Session, company_id: str) -> str:
    count = db.query(func.count(Customer.id)).filter(Customer.company_id == company_id).scalar() or 0

    for attempt in range(10):
        candidate = f"CUST-{count + 1 + attempt:06d}"
        exists = db.query(Customer.id).filter(
            Customer.company_id == company_id, Customer.customer_code == candidate
        ).first()
        if not exists:
            return candidate

    # Extremely unlikely fallback if the sequential scan collides repeatedly.
    return f"CUST-{gen_uuid_suffix()}"


def gen_uuid_suffix() -> str:
    import uuid
    return uuid.uuid4().hex[:8].upper()


def derive_segment(total_orders: int, total_revenue: Decimal) -> CustomerSegment:
    if total_orders >= VIP_MIN_ORDERS and total_revenue >= VIP_MIN_REVENUE:
        return CustomerSegment.VIP
    if total_orders >= LOYAL_MIN_ORDERS or total_revenue >= LOYAL_MIN_REVENUE:
        return CustomerSegment.LOYAL
    if total_orders >= REGULAR_MIN_ORDERS:
        return CustomerSegment.REGULAR
    return CustomerSegment.NEW


def log_customer_activity(db: Session, customer_id: str, company_id: str,
                           activity_type: CustomerActivityType, description: str):
    db.add(CustomerActivity(
        customer_id=customer_id, company_id=company_id,
        activity_type=activity_type, description=description,
    ))


def recalculate_purchase_summary(db: Session, customer_id: str) -> CustomerPurchaseSummary:
    """
    Recomputes a customer's purchase_summary row from scratch based on every
    Sale currently linked to them (customer_id FK). Called after any sale
    create/update/delete that touches a customer. Also re-derives the
    customer's segment and fires FIRST_PURCHASE / LARGE_PURCHASE / VIP
    activity + notification events when thresholds are newly crossed.
    """
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        return None

    summary = db.query(CustomerPurchaseSummary).filter(
        CustomerPurchaseSummary.customer_id == customer_id
    ).first()
    if not summary:
        summary = CustomerPurchaseSummary(customer_id=customer_id, company_id=customer.company_id)
        db.add(summary)
        db.flush()

    previous_orders = summary.total_orders
    previous_segment = customer.segment

    agg = db.query(
        func.count(func.distinct(Sale.id)),
        func.coalesce(func.sum(Sale.total_amount), 0),
        func.min(Sale.sale_date),
        func.max(Sale.sale_date),
    ).filter(Sale.customer_id == customer_id).first()

    total_orders, total_revenue, first_purchase, last_purchase = agg
    total_orders = total_orders or 0
    total_revenue = Decimal(total_revenue or 0)

    total_quantity = db.query(func.coalesce(func.sum(SaleItem.quantity), 0)).join(
        Sale, SaleItem.sale_id == Sale.id
    ).filter(Sale.customer_id == customer_id).scalar() or 0

    favorite_product_id = db.query(SaleItem.product_id).join(
        Sale, SaleItem.sale_id == Sale.id
    ).filter(Sale.customer_id == customer_id).group_by(SaleItem.product_id).order_by(
        func.sum(SaleItem.quantity).desc()
    ).limit(1).scalar()

    favorite_category_id = db.query(SaleItem.category_id).join(
        Sale, SaleItem.sale_id == Sale.id
    ).filter(Sale.customer_id == customer_id).group_by(SaleItem.category_id).order_by(
        func.sum(SaleItem.quantity).desc()
    ).limit(1).scalar()

    summary.total_orders = total_orders
    summary.total_revenue = total_revenue
    summary.total_quantity = total_quantity
    summary.average_order_value = (total_revenue / total_orders) if total_orders > 0 else Decimal("0")
    summary.first_purchase_date = first_purchase
    summary.last_purchase_date = last_purchase
    summary.favorite_product_id = favorite_product_id
    summary.favorite_category_id = favorite_category_id

    new_segment = derive_segment(total_orders, total_revenue)
    customer.segment = new_segment

    # -- First purchase: 0 -> 1 orders --
    if previous_orders == 0 and total_orders >= 1:
        log_customer_activity(
            db, customer_id, customer.company_id, CustomerActivityType.FIRST_PURCHASE,
            f"Made their first purchase (₹{total_revenue}).",
        )
        notify_roles(
            db, customer.company_id, NotificationType.CUSTOMER_FIRST_PURCHASE,
            title="First Purchase",
            message=f"{customer.full_name} ({customer.customer_code}) made their first purchase.",
            priority=NotificationPriority.LOW,
            customer_id=customer.id, resource_type="Customer", resource_id=customer.id,
        )

    # -- Most recent single sale large-purchase check --
    latest_sale = db.query(Sale).filter(Sale.customer_id == customer_id).order_by(
        Sale.sale_date.desc()
    ).first()
    if latest_sale and latest_sale.total_amount >= LARGE_PURCHASE_THRESHOLD:
        already_logged = db.query(CustomerActivity.id).filter(
            CustomerActivity.customer_id == customer_id,
            CustomerActivity.activity_type == CustomerActivityType.LARGE_PURCHASE,
            CustomerActivity.description.like(f"%{latest_sale.invoice_number}%"),
        ).first()
        if not already_logged:
            log_customer_activity(
                db, customer_id, customer.company_id, CustomerActivityType.LARGE_PURCHASE,
                f"Large purchase recorded: {latest_sale.invoice_number} (₹{latest_sale.total_amount}).",
            )

    # -- Segment upgraded to VIP --
    if new_segment == CustomerSegment.VIP and previous_segment != CustomerSegment.VIP:
        log_customer_activity(
            db, customer_id, customer.company_id, CustomerActivityType.SEGMENT_CHANGED,
            f"Upgraded to VIP segment (total revenue ₹{total_revenue}, {total_orders} orders).",
        )
        notify_roles(
            db, customer.company_id, NotificationType.CUSTOMER_VIP,
            title="VIP Customer",
            message=f"{customer.full_name} ({customer.customer_code}) is now a VIP customer.",
            priority=NotificationPriority.LOW,
            customer_id=customer.id, resource_type="Customer", resource_id=customer.id,
        )
    elif new_segment != previous_segment:
        log_customer_activity(
            db, customer_id, customer.company_id, CustomerActivityType.SEGMENT_CHANGED,
            f"Segment changed from {previous_segment.value} to {new_segment.value}.",
        )

    db.commit()
    db.refresh(summary)
    return summary


def scan_inactive_customers(db: Session, company_id: str) -> int:
    """
    Flags ACTIVE customers with a purchase history who haven't bought
    anything in INACTIVITY_DAYS. Creates at most one CUSTOMER_INACTIVE
    notification per customer per INACTIVITY_RENOTIFY_DAYS window.
    Called opportunistically when the Customer Analytics Dashboard loads
    (this project has no background job runner).
    """
    cutoff = datetime.utcnow() - timedelta(days=INACTIVITY_DAYS)
    renotify_cutoff = datetime.utcnow() - timedelta(days=INACTIVITY_RENOTIFY_DAYS)

    candidates = db.query(Customer, CustomerPurchaseSummary).join(
        CustomerPurchaseSummary, CustomerPurchaseSummary.customer_id == Customer.id
    ).filter(
        Customer.company_id == company_id,
        Customer.status == CustomerStatus.ACTIVE,
        CustomerPurchaseSummary.last_purchase_date.isnot(None),
        CustomerPurchaseSummary.last_purchase_date < cutoff,
    ).all()

    created = 0
    for customer, summary in candidates:
        recent_notice = db.query(Notification.id).filter(
            Notification.customer_id == customer.id,
            Notification.type == NotificationType.CUSTOMER_INACTIVE,
            Notification.created_at >= renotify_cutoff,
        ).first()
        if recent_notice:
            continue

        days_inactive = (datetime.utcnow() - summary.last_purchase_date).days
        notify_roles(
            db, company_id, NotificationType.CUSTOMER_INACTIVE,
            title="Inactive Customer",
            message=f"{customer.full_name} ({customer.customer_code}) hasn't purchased in {days_inactive} days.",
            priority=NotificationPriority.LOW,
            customer_id=customer.id, resource_type="Customer", resource_id=customer.id,
        )
        created += 1

    if created:
        db.commit()
    return created
