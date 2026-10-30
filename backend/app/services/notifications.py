"""
Task 14: Notification & Alert Management — business logic layer.

Design decisions, documented here since they're the things a reviewer
will ask about:

1. USER-SPECIFIC ROWS, NOT SHARED/BROADCAST ROWS.
   Every Notification row belongs to exactly one user (`user_id` is
   NOT NULL). A condition that should reach several people (e.g. "notify
   every Admin") is fanned out into one row per eligible user at
   creation time via `notify_roles()`. This is what makes "does
   notification 123 belong to the authenticated user" a plain WHERE
   clause instead of a shared-row-plus-per-user-read-state problem, and
   it's what the task's own security example ("must verify that
   notification 123 actually belongs to the authenticated user")
   implies.

2. ROLE MATRIX (who gets notified for what) — documented once, here:
     Admin    : stock alerts (low/out/stockout-risk/overstock),
                import completed/failed, system alerts, sales alerts
     Analyst  : stock alerts, sales alerts, forecast/insight alerts
     Viewer   : stock alerts only (read-only role, no import/system noise)
   SUPER_ADMIN is treated as COMPANY_ADMIN for notification purposes.

3. PRIORITY RULES (business rules, as the task asks to document):
     CRITICAL — current_stock == 0 (actual stockout)
     HIGH     — predicted to stock out soon (stockout risk from
                forecasting) or current_stock < reorder point with high
                sell-through
     MEDIUM   — current_stock <= reorder point but not an imminent risk
                (ordinary low-stock/reorder alert), or overstock
     LOW      — general system information (e.g. a completed import,
                a new customer registration)

4. DUPLICATE PREVENTION — `dedupe_key` + `upsert_condition_notification()`.
   Before inserting, this checks whether the same user already has an
   UNREAD notification with the same dedupe key (company + type +
   resource). If so, nothing new is created — the condition is still
   open and the user hasn't acknowledged it yet, so re-notifying would
   just be noise. Once they mark it read, a fresh evaluation is free to
   create a new one if the condition is still true.

5. LIFECYCLE / EXPIRY — `resolve_condition_notifications()`.
   When a condition clears (stock replenished above the reorder point),
   any still-unread notifications for that exact condition are
   auto-marked read. An old "stockout" alert has nothing more to tell
   you once the product is back in stock — this keeps the notification
   center reflecting current reality instead of accumulating stale alerts.
"""
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Notification, NotificationType, NotificationPriority,
    User, UserRole, UserStatus, Product, Inventory, StockStatus,
)

# Role matrix (see module docstring). SUPER_ADMIN always included alongside
# COMPANY_ADMIN since it's a superset role in this app.
ROLES_FOR_TYPE: dict[NotificationType, list[UserRole]] = {
    NotificationType.LOW_STOCK: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST, UserRole.VIEWER],
    NotificationType.OUT_OF_STOCK: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST, UserRole.VIEWER],
    NotificationType.STOCKOUT_RISK: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST, UserRole.VIEWER],
    NotificationType.OVERSTOCK: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST, UserRole.VIEWER],
    NotificationType.MANUAL_ADJUSTMENT: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST],
    NotificationType.SALES_ALERT: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST],
    NotificationType.CUSTOMER_REGISTERED: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST],
    NotificationType.CUSTOMER_VIP: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST],
    NotificationType.CUSTOMER_INACTIVE: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST],
    NotificationType.CUSTOMER_FIRST_PURCHASE: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST],
    NotificationType.FORECAST_STOCK_RUNOUT: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST],
    NotificationType.FORECAST_DEMAND_EXCEEDS_STOCK: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST],
    NotificationType.FORECAST_DEMAND_GROWTH: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST],
    NotificationType.IMPORT_COMPLETED: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN],
    NotificationType.IMPORT_FAILED: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN],
    NotificationType.DATA_IMPORT_COMPLETED: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN],
    NotificationType.SYSTEM_ALERT: [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN],
}

DEFAULT_ROLES: list[UserRole] = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN]


def notify_roles(
    db: Session, company_id: str, type: NotificationType, title: str, message: str,
    priority: NotificationPriority = NotificationPriority.LOW,
    product_id: Optional[str] = None, customer_id: Optional[str] = None,
    resource_type: Optional[str] = None, resource_id: Optional[str] = None,
    dedupe_key: Optional[str] = None, roles: Optional[list[UserRole]] = None,
) -> list[Notification]:
    """Fans a notification out to every active user in the company whose
    role is eligible for this notification type (see ROLES_FOR_TYPE)."""
    target_roles = roles if roles is not None else ROLES_FOR_TYPE.get(type, DEFAULT_ROLES)
    users = db.query(User).filter(
        User.company_id == company_id, User.role.in_(target_roles), User.status == UserStatus.ACTIVE
    ).all()

    created = []
    for user in users:
        n = _create_or_skip(
            db, company_id=company_id, user_id=user.id, type=type, title=title, message=message,
            priority=priority, product_id=product_id, customer_id=customer_id,
            resource_type=resource_type, resource_id=resource_id, dedupe_key=dedupe_key,
        )
        if n:
            created.append(n)
    return created


def notify_user(
    db: Session, company_id: str, user_id: str, type: NotificationType, title: str, message: str,
    priority: NotificationPriority = NotificationPriority.LOW,
    product_id: Optional[str] = None, customer_id: Optional[str] = None,
    resource_type: Optional[str] = None, resource_id: Optional[str] = None,
    dedupe_key: Optional[str] = None,
) -> Optional[Notification]:
    """Same as notify_roles but for one specific user (e.g. "the admin who
    started this import")."""
    return _create_or_skip(
        db, company_id=company_id, user_id=user_id, type=type, title=title, message=message,
        priority=priority, product_id=product_id, customer_id=customer_id,
        resource_type=resource_type, resource_id=resource_id, dedupe_key=dedupe_key,
    )


def _create_or_skip(
    db: Session, company_id: str, user_id: str, type: NotificationType, title: str, message: str,
    priority: NotificationPriority, product_id: Optional[str], customer_id: Optional[str],
    resource_type: Optional[str], resource_id: Optional[str], dedupe_key: Optional[str],
) -> Optional[Notification]:
    if dedupe_key:
        existing = db.query(Notification.id).filter(
            Notification.user_id == user_id, Notification.dedupe_key == dedupe_key,
            Notification.is_read.is_(False),
        ).first()
        if existing:
            return None  # condition already has an open, unread alert for this user

    entry = Notification(
        company_id=company_id, user_id=user_id, type=type, priority=priority,
        title=title, message=message, product_id=product_id, customer_id=customer_id,
        resource_type=resource_type, resource_id=resource_id, dedupe_key=dedupe_key,
    )
    db.add(entry)
    # SessionLocal uses autoflush=False, so flush explicitly: otherwise a second
    # call with the same dedupe_key in the same request wouldn't see this row.
    db.flush()
    return entry


def resolve_condition_notifications(db: Session, company_id: str, dedupe_key: str) -> int:
    """Auto-marks-read every still-open notification for a condition that
    has now cleared (e.g. stock replenished above reorder level). Returns
    the count resolved."""
    rows = db.query(Notification).filter(
        Notification.company_id == company_id, Notification.dedupe_key == dedupe_key,
        Notification.is_read.is_(False),
    ).all()
    for row in rows:
        row.is_read = True
        row.read_at = datetime.utcnow()
    return len(rows)


# ---------------------------------------------------------------- Inventory

def _stock_dedupe_key(product_id: str, condition: str) -> str:
    return f"stock:{product_id}:{condition}"


def evaluate_product_stock_alert(db: Session, company_id: str, inventory: Inventory, product: Product) -> None:
    """
    Evaluates ONE product's current stock against the priority rules
    (see module docstring) and creates/resolves notifications accordingly.
    Called both reactively (right after a stock-changing operation) and
    from a full scan (see evaluate_inventory_alerts) so newly-detected
    conditions are caught even if no one adjusted stock through the app
    since the condition first became true.
    """
    available = inventory.available_stock
    reorder_level = inventory.reorder_level

    if available <= 0:
        notify_roles(
            db, company_id, NotificationType.OUT_OF_STOCK,
            title="Out of Stock",
            message=f'"{product.name}" is now Out of Stock.',
            priority=NotificationPriority.CRITICAL,
            product_id=product.id, resource_type="Product", resource_id=product.id,
            dedupe_key=_stock_dedupe_key(product.id, "out_of_stock"),
        )
    else:
        resolve_condition_notifications(db, company_id, _stock_dedupe_key(product.id, "out_of_stock"))

    if 0 < available <= reorder_level:
        notify_roles(
            db, company_id, NotificationType.LOW_STOCK,
            title="Low Stock",
            message=f'"{product.name}" has fallen below its reorder point ({available} left, reorder at {reorder_level}).',
            priority=NotificationPriority.MEDIUM,
            product_id=product.id, resource_type="Product", resource_id=product.id,
            dedupe_key=_stock_dedupe_key(product.id, "low_stock"),
        )
    else:
        resolve_condition_notifications(db, company_id, _stock_dedupe_key(product.id, "low_stock"))

    # Overstock: more than 3x the reorder level sitting on the shelf.
    if reorder_level > 0 and available > reorder_level * 3:
        notify_roles(
            db, company_id, NotificationType.OVERSTOCK,
            title="Overstock",
            message=f'"{product.name}" is overstocked ({available} on hand, reorder level {reorder_level}).',
            priority=NotificationPriority.MEDIUM,
            product_id=product.id, resource_type="Product", resource_id=product.id,
            dedupe_key=_stock_dedupe_key(product.id, "overstock"),
        )
    else:
        resolve_condition_notifications(db, company_id, _stock_dedupe_key(product.id, "overstock"))


# Full scans are throttled per company: the notification endpoints are polled
# by the UI every ~15s per open tab, and re-checking every product that often
# adds nothing (stock changes already trigger evaluate_product_stock_alert
# reactively). In-process only — with several workers each may scan once per
# window, which is harmless because scans are idempotent.
SCAN_INTERVAL_SECONDS = 60
_last_scan: dict[str, float] = {}


def evaluate_inventory_alerts(db: Session, company_id: str, force: bool = False) -> int:
    """
    Full scan of every product's current inventory for this company —
    catches conditions that exist right now regardless of whether/when
    they were last triggered reactively. Cheap enough to run on-read
    (same pattern this codebase already uses for
    services.customers.scan_inactive_customers): a handful of comparisons
    per product, no external calls, and upsert_condition_notification
    means repeated scans are no-ops once a condition has an open alert.
    """
    now = time.monotonic()
    if not force and now - _last_scan.get(company_id, 0.0) < SCAN_INTERVAL_SECONDS:
        return 0
    _last_scan[company_id] = now

    rows = db.query(Inventory, Product).join(Product, Product.id == Inventory.product_id).filter(
        Inventory.company_id == company_id
    ).all()
    for inventory, product in rows:
        evaluate_product_stock_alert(db, company_id, inventory, product)
    return len(rows)


def evaluate_stockout_risk(db: Session, company_id: str, product: Product, days_of_stock_remaining, lead_time_days: int) -> None:
    """Called from forecast generation: HIGH-priority alert when a product
    is predicted to run out before a fresh order could even arrive."""
    key = _stock_dedupe_key(product.id, "stockout_risk")
    if days_of_stock_remaining is not None and days_of_stock_remaining < lead_time_days:
        notify_roles(
            db, company_id, NotificationType.STOCKOUT_RISK,
            title="Stockout Risk",
            message=f'"{product.name}" is expected to run out in about {days_of_stock_remaining} day(s), '
                    f'before a reorder could arrive ({lead_time_days}-day lead time).',
            priority=NotificationPriority.HIGH,
            product_id=product.id, resource_type="Product", resource_id=product.id,
            dedupe_key=key,
        )
    else:
        resolve_condition_notifications(db, company_id, key)
