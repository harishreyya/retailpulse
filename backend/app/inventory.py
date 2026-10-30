from fastapi import Request
from sqlalchemy.orm import Session

from app.models import Product, Notification, NotificationType
from app.audit import log_action


def check_stock_alerts(
    db: Session,
    request: Request,
    product: Product,
    company_id: str,
    user_id: str,
):
    """
    Call this after any stock_quantity change on a product (sale created,
    sale updated, sale deleted/reverted). Creates a notification and audit
    entry when the product crosses into low-stock or out-of-stock, and
    clears the out-of-stock flag if stock is replenished above zero.
    """
    if product.stock_quantity <= 0:
        if not product.is_out_of_stock:
            product.is_out_of_stock = True
            db.add(Notification(
                company_id=company_id,
                product_id=product.id,
                type=NotificationType.OUT_OF_STOCK,
                message=f"{product.name} ({product.sku}) is now out of stock.",
            ))
            log_action(db, request, "Product Marked Out of Stock", company_id=company_id,
                       user_id=user_id, entity_name=product.name)
    else:
        if product.is_out_of_stock:
            product.is_out_of_stock = False

        if product.stock_quantity <= product.low_stock_threshold:
            db.add(Notification(
                company_id=company_id,
                product_id=product.id,
                type=NotificationType.LOW_STOCK,
                message=f"{product.name} ({product.sku}) is low on stock: "
                        f"{product.stock_quantity} {product.unit_of_measure} remaining.",
            ))

    db.commit()