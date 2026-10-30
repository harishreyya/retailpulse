from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy import func, or_, asc, desc
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Product, Category, User, UserRole, ProductStatus
from app.schemas import ProductCreate, ProductUpdate, ProductOut, ProductListResponse, ProductOptionOut
from app.dependencies import require_roles, get_current_company_id
from app.audit import log_action

router = APIRouter(prefix="/products", tags=["products"])

ADMIN_ONLY = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN]
SALES_ROLES = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST]

SORT_FIELDS = {
    "name": Product.name,
    "price": Product.unit_price,
    "recent": Product.created_at,
}


def _get_category_or_404(db: Session, company_id: str, category_id: str) -> Category:
    category = db.query(Category).filter(
        Category.id == category_id, Category.company_id == company_id
    ).first()
    if not category:
        raise HTTPException(status_code=400, detail="Category not found")
    return category


@router.get("", response_model=ProductListResponse)
def list_products(
    search: Optional[str] = None,
    category_id: Optional[str] = None,
    status_filter: Optional[ProductStatus] = Query(None, alias="status"),
    brand: Optional[str] = None,
    sort_by: str = Query("recent", pattern="^(name|price|recent)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    query = db.query(Product).options(joinedload(Product.category)).filter(
        Product.company_id == company_id
    )

    if search:
        like = f"%{search}%"
        query = query.filter(or_(
            Product.name.ilike(like),
            Product.sku.ilike(like),
            Product.brand.ilike(like),
        ))

    if category_id:
        query = query.filter(Product.category_id == category_id)

    if status_filter:
        query = query.filter(Product.status == status_filter)

    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))

    total = query.count()

    sort_column = SORT_FIELDS[sort_by]
    order_fn = asc if sort_dir == "asc" else desc
    query = query.order_by(order_fn(sort_column))

    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return ProductListResponse(items=items, total=total)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    _get_category_or_404(db, company_id, payload.category_id)

    duplicate_sku = db.query(Product).filter(
        Product.company_id == company_id,
        func.lower(Product.sku) == payload.sku.lower(),
    ).first()
    if duplicate_sku:
        raise HTTPException(status_code=400, detail=f"SKU '{payload.sku}' already exists for this company")

    duplicate_name = db.query(Product).filter(
        Product.company_id == company_id,
        Product.category_id == payload.category_id,
        func.lower(Product.name) == payload.name.lower(),
    ).first()
    if duplicate_name:
        raise HTTPException(status_code=400, detail="A product with this name already exists in this category")

    product = Product(
        company_id=company_id,
        category_id=payload.category_id,
        name=payload.name,
        sku=payload.sku,
        brand=payload.brand,
        description=payload.description,
        unit_price=payload.unit_price,
        cost_price=payload.cost_price,
        stock_quantity=payload.stock_quantity,
        unit_of_measure=payload.unit_of_measure,
        status=payload.status,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    # Initialize inventory record for the new product
    from app.models.inventory import Inventory
    from app.schemas.inventory_utils import DEFAULT_REORDER_LEVEL
    inv = Inventory(
        company_id=company_id,
        product_id=product.id,
        current_stock=product.stock_quantity,
        reserved_stock=0,
        reorder_level=DEFAULT_REORDER_LEVEL,
    )
    inv.update_status()
    db.add(inv)
    db.commit()

    log_action(db, request, "Product Created", company_id=company_id,
               user_id=current_user.id, entity_name=product.name,
               resource_type="Product", resource_id=product.id,
               after={"name": product.name, "sku": product.sku, "unit_price": str(product.unit_price),
                      "stock_quantity": product.stock_quantity, "status": product.status.value})
    db.commit()

    return product


@router.get("/sales-options", response_model=list[ProductOptionOut])
def list_product_options_for_sale(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SALES_ROLES)),
):
    """
    Lightweight, active-only product list for the sales-entry product
    picker. Available to Analysts as well as Admins, unlike the full
    product management endpoints above. Inactive products are excluded
    per Task 2's requirement that they not be selectable for future
    transactions.
    """
    query = db.query(Product).options(joinedload(Product.category)).filter(
        Product.company_id == company_id,
        Product.status == ProductStatus.ACTIVE,
    )
    if search:
        like = f"%{search}%"
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))

    return query.order_by(Product.name.asc()).limit(50).all()


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    product = db.query(Product).options(joinedload(Product.category)).filter(
        Product.id == product_id, Product.company_id == company_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: str,
    payload: ProductUpdate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    product = db.query(Product).filter(
        Product.id == product_id, Product.company_id == company_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = payload.model_dump(exclude_unset=True)

    # Cross-field validation against the merged (existing + incoming) state,
    # since PATCH-style partial updates may only send one of the two prices.
    new_unit_price = update_data.get("unit_price", product.unit_price)
    new_cost_price = update_data.get("cost_price", product.cost_price)
    if new_cost_price > new_unit_price:
        raise HTTPException(status_code=400, detail="Cost Price cannot exceed Unit Price")

    if "category_id" in update_data:
        _get_category_or_404(db, company_id, update_data["category_id"])

    if "sku" in update_data and update_data["sku"].lower() != product.sku.lower():
        duplicate_sku = db.query(Product).filter(
            Product.company_id == company_id,
            func.lower(Product.sku) == update_data["sku"].lower(),
            Product.id != product_id,
        ).first()
        if duplicate_sku:
            raise HTTPException(status_code=400, detail=f"SKU '{update_data['sku']}' already exists for this company")

    new_name = update_data.get("name", product.name)
    new_category_id = update_data.get("category_id", product.category_id)
    if new_name.lower() != product.name.lower() or new_category_id != product.category_id:
        duplicate_name = db.query(Product).filter(
            Product.company_id == company_id,
            Product.category_id == new_category_id,
            func.lower(Product.name) == new_name.lower(),
            Product.id != product_id,
        ).first()
        if duplicate_name:
            raise HTTPException(status_code=400, detail="A product with this name already exists in this category")

    previous_status = product.status
    before_snapshot = {field: getattr(product, field) for field in update_data}

    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    after_snapshot = {field: getattr(product, field) for field in update_data}

    log_action(db, request, "Product Updated", company_id=company_id,
               user_id=current_user.id, entity_name=product.name,
               resource_type="Product", resource_id=product.id,
               before=before_snapshot, after=after_snapshot)

    if "status" in update_data and update_data["status"] != previous_status:
        action = "Product Activated" if product.status == ProductStatus.ACTIVE else "Product Deactivated"
        log_action(db, request, action, company_id=company_id,
                   user_id=current_user.id, entity_name=product.name,
                   resource_type="Product", resource_id=product.id,
                   before={"status": previous_status.value}, after={"status": product.status.value})

    db.commit()
    return product


@router.patch("/{product_id}/status", response_model=ProductOut)
def toggle_product_status(
    product_id: str,
    new_status: ProductStatus,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    product = db.query(Product).filter(
        Product.id == product_id, Product.company_id == company_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    previous_status = product.status
    product.status = new_status
    db.commit()
    db.refresh(product)

    action = "Product Activated" if new_status == ProductStatus.ACTIVE else "Product Deactivated"
    log_action(db, request, action, company_id=company_id,
               user_id=current_user.id, entity_name=product.name,
               resource_type="Product", resource_id=product.id,
               before={"status": previous_status.value}, after={"status": product.status.value})
    db.commit()

    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: str,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    product = db.query(Product).filter(
        Product.id == product_id, Product.company_id == company_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product_name = product.name
    product_id = product.id
    db.delete(product)
    db.commit()

    log_action(db, request, "Product Deleted", company_id=company_id,
               user_id=current_user.id, entity_name=product_name,
               resource_type="Product", resource_id=product_id)
    db.commit()

    return None
