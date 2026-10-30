from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, Category, ProductStatus, User
from app.schemas import DashboardSummary
from app.dependencies import get_current_company_id, get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    total_products = db.query(func.count(Product.id)).filter(
        Product.company_id == company_id
    ).scalar() or 0

    active_products = db.query(func.count(Product.id)).filter(
        Product.company_id == company_id,
        Product.status == ProductStatus.ACTIVE,
    ).scalar() or 0

    total_categories = db.query(func.count(Category.id)).filter(
        Category.company_id == company_id
    ).scalar() or 0

    return DashboardSummary(
        total_products=total_products,
        active_products=active_products,
        inactive_products=total_products - active_products,
        total_categories=total_categories,
    )
