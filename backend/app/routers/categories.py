from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category, Product, User, UserRole
from app.schemas import CategoryCreate, CategoryUpdate, CategoryOut
from app.dependencies import require_roles, get_current_company_id
from app.audit import log_action

router = APIRouter(prefix="/categories", tags=["categories"])

ADMIN_ONLY = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN]


def _serialize(category: Category, product_count: int) -> CategoryOut:
    return CategoryOut(
        id=category.id,
        name=category.name,
        description=category.description,
        status=category.status,
        product_count=product_count,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


@router.get("", response_model=list[CategoryOut])
def list_categories(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    query = db.query(
        Category, func.count(Product.id).label("product_count")
    ).outerjoin(Product, Product.category_id == Category.id).filter(
        Category.company_id == company_id
    )

    if search:
        query = query.filter(Category.name.ilike(f"%{search}%"))

    query = query.group_by(Category.id).order_by(Category.name.asc())

    return [_serialize(category, count) for category, count in query.all()]


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    existing = db.query(Category).filter(
        Category.company_id == company_id,
        func.lower(Category.name) == payload.name.lower(),
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="A category with this name already exists")

    category = Category(
        company_id=company_id,
        name=payload.name,
        description=payload.description,
        status=payload.status,
    )
    db.add(category)
    db.commit()
    db.refresh(category)

    log_action(db, request, "Category Created", company_id=company_id,
               user_id=current_user.id, entity_name=category.name)
    db.commit()

    return _serialize(category, 0)


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: str,
    payload: CategoryUpdate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    category = db.query(Category).filter(
        Category.id == category_id, Category.company_id == company_id
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    if payload.name and payload.name.lower() != category.name.lower():
        duplicate = db.query(Category).filter(
            Category.company_id == company_id,
            func.lower(Category.name) == payload.name.lower(),
            Category.id != category_id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="A category with this name already exists")

    update_data = payload.model_dump(exclude_unset=True)
    before_snapshot = {field: getattr(category, field) for field in update_data}

    for field, value in update_data.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)

    after_snapshot = {field: getattr(category, field) for field in update_data}
    product_count = db.query(func.count(Product.id)).filter(Product.category_id == category.id).scalar()

    log_action(db, request, "Category Updated", company_id=company_id,
               user_id=current_user.id, entity_name=category.name,
               resource_type="Category", resource_id=category.id,
               before=before_snapshot, after=after_snapshot)
    db.commit()

    return _serialize(category, product_count or 0)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: str,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(ADMIN_ONLY)),
):
    category = db.query(Category).filter(
        Category.id == category_id, Category.company_id == company_id
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    product_count = db.query(func.count(Product.id)).filter(Product.category_id == category.id).scalar()
    if product_count and product_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete category with {product_count} product(s) assigned to it. "
                   "Reassign or delete those products first.",
        )

    category_name = category.name
    db.delete(category)
    db.commit()

    log_action(db, request, "Category Deleted", company_id=company_id,
               user_id=current_user.id, entity_name=category_name)
    db.commit()

    return None
