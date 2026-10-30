from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Notification, NotificationType, NotificationPriority, User, Inventory, DemandForecast
from app.schemas import NotificationOut, NotificationListResponse, UnreadCountResponse, MarkAllReadResponse
from app.dependencies import get_current_company_id, get_current_user
from app.audit import log_action
from app.services.notifications import evaluate_inventory_alerts

router = APIRouter(prefix="/notifications", tags=["notifications"])

# UI-facing groupings for the Type filter (Stock / Sales / Import / System).
CATEGORY_TYPES: dict[str, list[NotificationType]] = {
    "stock": [
        NotificationType.LOW_STOCK, NotificationType.OUT_OF_STOCK, NotificationType.STOCKOUT_RISK,
        NotificationType.OVERSTOCK, NotificationType.MANUAL_ADJUSTMENT,
        NotificationType.FORECAST_STOCK_RUNOUT, NotificationType.FORECAST_DEMAND_EXCEEDS_STOCK,
    ],
    "sales": [
        NotificationType.SALES_ALERT, NotificationType.FORECAST_DEMAND_GROWTH,
        NotificationType.CUSTOMER_REGISTERED, NotificationType.CUSTOMER_VIP,
        NotificationType.CUSTOMER_INACTIVE, NotificationType.CUSTOMER_FIRST_PURCHASE,
    ],
    "import": [NotificationType.IMPORT_COMPLETED, NotificationType.IMPORT_FAILED, NotificationType.DATA_IMPORT_COMPLETED],
    "system": [NotificationType.SYSTEM_ALERT],
}


def _get_own_notification_or_404(db: Session, user_id: str, notification_id: str) -> Notification:
    # user_id is part of the WHERE clause itself -- a request for another
    # user's notification id simply matches nothing, rather than being
    # checked (and possibly gotten wrong) after the fact. This is what the
    # task's "must verify notification 123 actually belongs to the
    # authenticated user" requirement means in practice.
    entry = db.query(Notification).filter(
        Notification.id == notification_id, Notification.user_id == user_id
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Notification not found")
    return entry


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    unread_only: bool = False,
    is_read: Optional[bool] = None,
    category: Optional[str] = Query(None, pattern="^(stock|sales|import|system)$"),
    type: Optional[NotificationType] = None,
    priority: Optional[NotificationPriority] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    # On-read evaluation, same pattern as customers.scan_inactive_customers:
    # catches stock conditions even if nothing was adjusted through the app
    # since they became true. Cheap (a handful of comparisons per product)
    # and idempotent (dedupe_key means repeated calls are no-ops).
    evaluate_inventory_alerts(db, company_id)
    db.commit()

    query = db.query(Notification).options(
        joinedload(Notification.product), joinedload(Notification.customer)
    ).filter(Notification.company_id == company_id, Notification.user_id == current_user.id)

    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    if is_read is not None:
        query = query.filter(Notification.is_read.is_(is_read))
    if category:
        query = query.filter(Notification.type.in_(CATEGORY_TYPES[category]))
    if type:
        query = query.filter(Notification.type == type)
    if priority:
        query = query.filter(Notification.priority == priority)

    total = query.count()
    unread_count = db.query(Notification).filter(
        Notification.company_id == company_id, Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    ).count()

    items = (
        query.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size).all()
    )

    return NotificationListResponse(
        items=items, total=total, unread_count=unread_count, page=page, page_size=page_size,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    evaluate_inventory_alerts(db, company_id)
    db.commit()

    count = db.query(Notification).filter(
        Notification.company_id == company_id, Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    ).count()
    return UnreadCountResponse(unread_count=count)


@router.get("/{notification_id}", response_model=NotificationOut)
def get_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    entry = _get_own_notification_or_404(db, current_user.id, notification_id)
    if entry.company_id != company_id:
        raise HTTPException(status_code=404, detail="Notification not found")

    out = NotificationOut.model_validate(entry)
    out.details = _build_details(db, company_id, entry)
    return out


def _build_details(db: Session, company_id: str, entry: Notification) -> Optional[dict]:
    """Extra context for stock-related alerts (current stock, reorder
    point, risk, recommended quantity). Read from live inventory and the
    latest forecast, company-scoped."""
    if not entry.product_id:
        return None
    details: dict = {}
    inv = db.query(Inventory).filter(
        Inventory.company_id == company_id, Inventory.product_id == entry.product_id
    ).first()
    if inv:
        details["current_stock"] = inv.available_stock
        details["reorder_level"] = inv.reorder_level
        details["stock_status"] = inv.stock_status.value
    fc = db.query(DemandForecast).filter(
        DemandForecast.company_id == company_id, DemandForecast.product_id == entry.product_id
    ).order_by(DemandForecast.generated_at.desc()).first()
    if fc:
        details["reorder_point"] = fc.reorder_point
        details["risk"] = fc.stock_risk.value if fc.stock_risk else None
        details["recommended_quantity"] = fc.recommended_reorder_quantity
        details["days_of_stock_remaining"] = str(fc.days_of_stock_remaining) if fc.days_of_stock_remaining is not None else None
    return details or None


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    entry = _get_own_notification_or_404(db, current_user.id, notification_id)
    if entry.company_id != company_id:
        raise HTTPException(status_code=404, detail="Notification not found")

    if not entry.is_read:
        entry.is_read = True
        entry.read_at = datetime.utcnow()
        db.commit()
        db.refresh(entry)
    return entry


@router.patch("/read-all", response_model=MarkAllReadResponse)
def mark_all_read(
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    # Only touches rows that are actually still unread (task: "prevent
    # already-read notifications from being unnecessarily updated").
    rows = db.query(Notification).filter(
        Notification.company_id == company_id, Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    ).all()
    now = datetime.utcnow()
    for row in rows:
        row.is_read = True
        row.read_at = now

    # A bulk action is worth an audit trail entry; marking one notification
    # read is routine UI noise and isn't logged individually.
    if rows:
        log_action(db, request, "Notifications Marked All Read", company_id=company_id,
                   user_id=current_user.id, resource_type="Notification",
                   details=f"{len(rows)} notifications")
    db.commit()
    return MarkAllReadResponse(updated_count=len(rows))
