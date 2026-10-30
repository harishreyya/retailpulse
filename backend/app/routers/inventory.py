from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy import func, or_, asc, desc
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    Inventory, InventoryMovement, Product, Category, User, UserRole,
    StockStatus, AdjustmentType, AdjustmentDirection, MovementType,
    NotificationType, NotificationPriority,
)
from app.services.notifications import notify_roles, evaluate_product_stock_alert
from app.schemas import (
    InventoryOut, InventoryProductOut, InventoryListResponse, ReorderLevelUpdate,
    StockAdjustmentCreate, MovementOut, MovementPerformerOut, MovementListResponse,
    CategoryBreakdown, StatusBreakdown, InventoryDashboardSummary,
)
from app.dependencies import require_roles, get_current_company_id
from app.audit import log_action
from app.services.inventory_utils import compute_stock_status

router = APIRouter(prefix="/inventory", tags=["inventory"])

VIEW_ROLES = [UserRole.COMPANY_ADMIN, UserRole.ANALYST, UserRole.SUPER_ADMIN]
ADMIN_ONLY = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN]

SORT_FIELDS = {
    "name": Product.name,
    "stock": Inventory.current_stock,
    "updated": Inventory.updated_at,
}


# ---------- Serialization helpers ----------

def _serialize_inventory(inv: Inventory) -> InventoryOut:
    product = inv.product
    return InventoryOut(
        id=inv.id,
        product=InventoryProductOut(
            id=product.id,
            name=product.name,
            sku=product.sku,
            brand=product.brand,
            unit_of_measure=product.unit_of_measure,
            category_id=product.category_id,
            category_name=product.category.name,
        ),
        current_stock=inv.current_stock,
        reserved_stock=inv.reserved_stock,
        available_stock=inv.available_stock,
        reorder_level=inv.reorder_level,
        stock_status=inv.stock_status,
        updated_at=inv.updated_at,
    )


def _serialize_movement(movement: InventoryMovement) -> MovementOut:
    return MovementOut(
        id=movement.id,
        movement_type=movement.movement_type,
        quantity_changed=movement.quantity_changed,
        previous_quantity=movement.previous_quantity,
        updated_quantity=movement.updated_quantity,
        reason=movement.reason,
        remarks=movement.remarks,
        performed_by=(
            MovementPerformerOut(id=movement.performer.id, name=movement.performer.name)
            if movement.performer else None
        ),
        created_at=movement.created_at,
    )


def _get_inventory_or_404(db: Session, company_id: str, inventory_id: str) -> Inventory:
    inv = db.query(Inventory).options(
        joinedload(Inventory.product).joinedload(Product.category)
    ).filter(
        Inventory.id == inventory_id, Inventory.company_id == company_id
    ).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory record not found")
    return inv


def _notify_status_change(db: Session, company_id: str, inventory: Inventory, previous_status: StockStatus):
    if inventory.stock_status != previous_status:
        evaluate_product_stock_alert(db, company_id, inventory, inventory.product)


# ---------- Static routes (must be declared before /{inventory_id}) ----------

@router.get("/dashboard", response_model=InventoryDashboardSummary)
def inventory_dashboard(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(VIEW_ROLES)),
):
    base = db.query(Inventory).filter(Inventory.company_id == company_id)

    total_products = base.count()
    total_quantity = db.query(func.coalesce(func.sum(Inventory.current_stock), 0)).filter(
        Inventory.company_id == company_id
    ).scalar() or 0
    low_stock_count = base.filter(Inventory.stock_status == StockStatus.LOW_STOCK).count()
    out_of_stock_count = base.filter(Inventory.stock_status == StockStatus.OUT_OF_STOCK).count()

    by_category_rows = db.query(
        Category.name, func.coalesce(func.sum(Inventory.current_stock), 0)
    ).join(Product, Product.category_id == Category.id).join(
        Inventory, Inventory.product_id == Product.id
    ).filter(Inventory.company_id == company_id).group_by(Category.name).order_by(Category.name.asc()).all()

    by_status_rows = db.query(
        Inventory.stock_status, func.count(Inventory.id)
    ).filter(Inventory.company_id == company_id).group_by(Inventory.stock_status).all()

    return InventoryDashboardSummary(
        total_products=total_products,
        total_quantity=int(total_quantity),
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        by_category=[CategoryBreakdown(category=c, quantity=int(q)) for c, q in by_category_rows],
        by_status=[StatusBreakdown(status=s, count=c) for s, c in by_status_rows],
    )


@router.get("/brands", response_model=list[str])
def list_inventory_brands(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(VIEW_ROLES)),
):
    rows = db.query(Product.brand).filter(
        Product.company_id == company_id, Product.brand.isnot(None), Product.brand != "",
    ).distinct().all()
    return sorted({r[0] for r in rows if r[0]})


@router.get("/categories", response_model=list[dict])
def list_inventory_categories(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(VIEW_ROLES)),
):
    # Analysts can view Inventory but not the admin-only /categories endpoint,
    # so the filter dropdown sources its options from here instead.
    rows = db.query(Category.id, Category.name).filter(
        Category.company_id == company_id
    ).order_by(Category.name.asc()).all()
    return [{"id": cid, "name": name} for cid, name in rows]


@router.get("/movements", response_model=MovementListResponse)
def list_all_movements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(VIEW_ROLES)),
):
    query = db.query(InventoryMovement).join(
        Inventory, InventoryMovement.inventory_id == Inventory.id
    ).options(joinedload(InventoryMovement.performer)).filter(
        Inventory.company_id == company_id
    ).order_by(desc(InventoryMovement.created_at))

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return MovementListResponse(items=[_serialize_movement(m) for m in items], total=total)


# ---------- Inventory list ----------

@router.get("", response_model=InventoryListResponse)
def list_inventory(
    search: Optional[str] = None,
    category_id: Optional[str] = None,
    brand: Optional[str] = None,
    stock_status: Optional[StockStatus] = Query(None, alias="status"),
    sort_by: str = Query("updated", pattern="^(name|stock|updated)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(VIEW_ROLES)),
):
    query = db.query(Inventory).join(Product, Inventory.product_id == Product.id).options(
        joinedload(Inventory.product).joinedload(Product.category)
    ).filter(Inventory.company_id == company_id)

    if search:
        like = f"%{search}%"
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))

    if category_id:
        query = query.filter(Product.category_id == category_id)

    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))

    if stock_status:
        query = query.filter(Inventory.stock_status == stock_status)

    total = query.count()

    sort_column = SORT_FIELDS[sort_by]
    order_fn = asc if sort_dir == "asc" else desc
    query = query.order_by(order_fn(sort_column))

    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return InventoryListResponse(items=[_serialize_inventory(inv) for inv in items], total=total)


# ---------- Per-record routes ----------

@router.get("/{inventory_id}/movements", response_model=MovementListResponse)
def list_movements(
    inventory_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(VIEW_ROLES)),
):
    inventory = _get_inventory_or_404(db, company_id, inventory_id)

    query = db.query(InventoryMovement).options(joinedload(InventoryMovement.performer)).filter(
        InventoryMovement.inventory_id == inventory.id
    ).order_by(desc(InventoryMovement.created_at))

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return MovementListResponse(items=[_serialize_movement(m) for m in items], total=total)


@router.post("/{inventory_id}/adjust", response_model=InventoryOut)
def adjust_stock(
    inventory_id: str,
    payload: StockAdjustmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    inventory = _get_inventory_or_404(db, company_id, inventory_id)
    product = inventory.product

    if payload.adjustment_type == AdjustmentType.STOCK_IN:
        movement_type = MovementType.STOCK_ADDITION
        delta = payload.quantity
    elif payload.adjustment_type == AdjustmentType.STOCK_OUT:
        movement_type = MovementType.STOCK_REMOVAL
        delta = -payload.quantity
    else:
        movement_type = MovementType.MANUAL_ADJUSTMENT
        delta = payload.quantity if payload.direction == AdjustmentDirection.INCREASE else -payload.quantity

    if delta < 0 and abs(delta) > inventory.available_stock:
        raise HTTPException(status_code=400, detail="Stock Out quantity cannot exceed available stock")

    previous_quantity = inventory.current_stock
    new_current = previous_quantity + delta
    if new_current < 0:
        raise HTTPException(status_code=400, detail="Stock quantity cannot become negative")

    previous_status = inventory.stock_status

    inventory.current_stock = new_current
    inventory.available_stock = max(0, new_current - inventory.reserved_stock)
    inventory.stock_status = compute_stock_status(inventory.available_stock, inventory.reorder_level)

    # Keep the Product catalog's stock_quantity field (Task 2/3) in sync.
    product.stock_quantity = new_current

    movement = InventoryMovement(
        inventory_id=inventory.id,
        movement_type=movement_type,
        quantity_changed=delta,
        previous_quantity=previous_quantity,
        updated_quantity=new_current,
        reason=payload.reason,
        remarks=payload.remarks,
        performed_by=current_user.id,
    )
    db.add(movement)

    _notify_status_change(db, company_id, inventory, previous_status)

    is_manual = movement_type == MovementType.MANUAL_ADJUSTMENT
    if is_manual:
        notify_roles(
            db, company_id, NotificationType.MANUAL_ADJUSTMENT,
            title="Manual Stock Adjustment",
            message=f'Stock for "{product.name}" was manually adjusted ({delta:+d}).',
            priority=NotificationPriority.LOW,
            product_id=product.id, resource_type="Product", resource_id=product.id,
        )

    db.commit()
    db.refresh(inventory)

    action_map = {
        MovementType.STOCK_ADDITION: "Stock Added",
        MovementType.STOCK_REMOVAL: "Stock Removed",
        MovementType.MANUAL_ADJUSTMENT: "Stock Adjusted",
    }
    log_action(
        db, request, action_map[movement_type],
        company_id=company_id, user_id=current_user.id,
        entity_name=product.name,
        details=f"Stock {'increased' if delta > 0 else 'decreased'} from {new_current - delta} to {new_current}",
        resource_type="Product", resource_id=product.id,
        before={"stock_quantity": new_current - delta}, after={"stock_quantity": new_current},
    )
    db.commit()

    return _serialize_inventory(inventory)


@router.put("/{inventory_id}/reorder-level", response_model=InventoryOut)
def update_reorder_level(
    inventory_id: str,
    payload: ReorderLevelUpdate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    inventory = _get_inventory_or_404(db, company_id, inventory_id)
    product = inventory.product

    previous_status = inventory.stock_status
    inventory.reorder_level = payload.reorder_level
    inventory.stock_status = compute_stock_status(inventory.available_stock, inventory.reorder_level)

    _notify_status_change(db, company_id, inventory, previous_status)

    db.commit()
    db.refresh(inventory)

    log_action(
        db, request, "Reorder Level Updated",
        company_id=company_id, user_id=current_user.id,
        entity_name=product.name,
        details=f"Reorder level set to {payload.reorder_level}",
    )
    db.commit()

    return _serialize_inventory(inventory)
