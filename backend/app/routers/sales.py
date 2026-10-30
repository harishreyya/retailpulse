from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy import func, or_, asc, desc
from sqlalchemy.exc import IntegrityError, DataError
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    Sale, SaleItem, Product, ProductStatus, User, UserRole,
    SalesChannel, PaymentMethod, PaymentStatus, Customer,
)
from app.models.inventory import Inventory, InventoryMovement, MovementType, StockStatus
from app.services.notifications import evaluate_product_stock_alert
from app.schemas import (
    SaleCreate, SaleUpdate, SaleOut, SaleListResponse, SalesDashboardSummary,
)
from app.dependencies import require_roles, get_current_company_id
from app.audit import log_action
from app.services.customers import recalculate_purchase_summary

router = APIRouter(prefix="/sales", tags=["sales"])

# Task 3: Company Admins AND Analysts can manage sales (wider than the
# admin-only Product/Category modules from Task 2).
SALES_ROLES = [UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN, UserRole.ANALYST]

SORT_FIELDS = {
    "date": Sale.sale_date,
    "invoice": Sale.invoice_number,
    "total": Sale.total_amount,
    "customer": Sale.customer_name,
}


def _generate_invoice_number(db: Session, company_id: str) -> str:
    year = datetime.utcnow().year
    prefix = f"INV-{year}-"

    count = db.query(func.count(Sale.id)).filter(
        Sale.company_id == company_id,
        Sale.invoice_number.like(f"{prefix}%"),
    ).scalar() or 0

    for attempt in range(10):
        candidate = f"{prefix}{count + 1 + attempt:06d}"
        exists = db.query(Sale.id).filter(
            Sale.company_id == company_id, Sale.invoice_number == candidate
        ).first()
        if not exists:
            return candidate

    raise HTTPException(status_code=500, detail="Could not generate a unique invoice number, please retry")


def record_sale_stock_movement(db: Session, product_id: str, company_id: str, quantity_changed: int, invoice_number: str, performed_by_id: str):
    inventory = db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.company_id == company_id
    ).first()
    
    if not inventory:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return
        from app.services.inventory_utils import DEFAULT_REORDER_LEVEL
        inventory = Inventory(
            company_id=company_id,
            product_id=product_id,
            current_stock=product.stock_quantity + (-quantity_changed),
            reserved_stock=0,
            reorder_level=DEFAULT_REORDER_LEVEL,
        )
        db.add(inventory)
        db.flush()
        
    previous_qty = inventory.current_stock
    new_qty = previous_qty + quantity_changed
    if new_qty < 0:
        new_qty = 0
        
    inventory.current_stock = new_qty
    old_status = inventory.stock_status
    inventory.update_status()
    db.add(inventory)
    
    if quantity_changed < 0:
        reason = f"Deducted {abs(quantity_changed)} units for Sale (Invoice: {invoice_number})"
        mov_type = MovementType.SALE
    else:
        reason = f"Reverted {quantity_changed} units for Sale change/deletion (Invoice: {invoice_number})"
        mov_type = MovementType.SALE

    movement = InventoryMovement(
        inventory_id=inventory.id,
        movement_type=mov_type,
        quantity_changed=quantity_changed,
        previous_quantity=previous_qty,
        updated_quantity=new_qty,
        reason=reason,
        performed_by=performed_by_id
    )
    db.add(movement)
    
    if old_status != inventory.stock_status:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product:
            evaluate_product_stock_alert(db, company_id, inventory, product)


def _build_items(db: Session, company_id: str, items_payload, products_cache: dict):
    """
    Validates each line item against its product (active, sufficient stock,
    discount within line value), auto-fills category, deducts stock, and
    returns (SaleItem objects not yet attached to a Sale, total_amount).
    Mutates products_cache in place so callers can run stock-alert checks
    after commit.
    """
    sale_items = []
    total_amount = Decimal("0")

    for line in items_payload:
        if not line.product_id:
            raise HTTPException(status_code=400, detail="Every line item must have a product selected")

        try:
            product = db.query(Product).filter(
                Product.id == line.product_id, Product.company_id == company_id
            ).first()
        except DataError:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Invalid product reference: {line.product_id}")
        if not product:
            raise HTTPException(status_code=400, detail=f"Product not found: {line.product_id}")

        if product.status != ProductStatus.ACTIVE:
            raise HTTPException(
                status_code=400,
                detail=f"'{product.name}' is inactive and cannot be sold",
            )

        if line.quantity > product.stock_quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for '{product.name}'. Available: {product.stock_quantity}",
            )

        unit_price = line.unit_price if line.unit_price is not None else product.unit_price
        line_value = line.quantity * unit_price
        if line.discount > line_value:
            raise HTTPException(
                status_code=400,
                detail=f"Discount cannot exceed total product value for '{product.name}'",
            )

        line_total = line_value - line.discount + line.tax

        product.stock_quantity -= line.quantity
        products_cache[product.id] = product

        sale_items.append(SaleItem(
            product_id=product.id,
            category_id=product.category_id,
            quantity=line.quantity,
            unit_price=unit_price,
            discount=line.discount,
            tax=line.tax,
            total=line_total,
        ))
        total_amount += line_total

    return sale_items, total_amount


def _serialize_list_item(sale: Sale) -> dict:
    return {
        "id": sale.id,
        "invoice_number": sale.invoice_number,
        "customer_name": sale.customer_name,
        "customer_id": sale.customer_id,
        "sale_date": sale.sale_date,
        "sales_channel": sale.sales_channel,
        "payment_method": sale.payment_method,
        "payment_status": sale.payment_status,
        "total_amount": sale.total_amount,
        "item_count": len(sale.items),
    }


@router.get("", response_model=SaleListResponse)
def list_sales(
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_id: Optional[str] = None,
    product_id: Optional[str] = None,
    brand: Optional[str] = None,
    sales_channel: Optional[SalesChannel] = None,
    payment_method: Optional[PaymentMethod] = None,
    payment_status: Optional[PaymentStatus] = None,
    sort_by: str = Query("date", pattern="^(date|invoice|total|customer)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SALES_ROLES)),
):
    query = db.query(Sale).options(joinedload(Sale.items)).filter(Sale.company_id == company_id)

    if search:
        like = f"%{search}%"
        matching_sale_ids = db.query(SaleItem.sale_id).join(
            Product, SaleItem.product_id == Product.id
        ).filter(Product.name.ilike(like)).subquery()

        query = query.filter(or_(
            Sale.invoice_number.ilike(like),
            Sale.customer_name.ilike(like),
            Sale.id.in_(db.query(matching_sale_ids.c.sale_id)),
        ))

    if category_id:
        matching_sale_ids = db.query(SaleItem.sale_id).filter(
            SaleItem.category_id == category_id
        ).subquery()
        query = query.filter(Sale.id.in_(db.query(matching_sale_ids.c.sale_id)))

    if product_id:
        matching_sale_ids = db.query(SaleItem.sale_id).filter(
            SaleItem.product_id == product_id
        ).subquery()
        query = query.filter(Sale.id.in_(db.query(matching_sale_ids.c.sale_id)))

    if brand:
        matching_sale_ids = db.query(SaleItem.sale_id).join(
            Product, SaleItem.product_id == Product.id
        ).filter(Product.brand == brand).subquery()
        query = query.filter(Sale.id.in_(db.query(matching_sale_ids.c.sale_id)))

    if date_from:
        query = query.filter(Sale.sale_date >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Sale.sale_date <= datetime.combine(date_to, datetime.max.time()))

    if sales_channel:
        query = query.filter(Sale.sales_channel == sales_channel)
    if payment_method:
        query = query.filter(Sale.payment_method == payment_method)
    if payment_status:
        query = query.filter(Sale.payment_status == payment_status)

    total = query.distinct().count()

    sort_column = SORT_FIELDS[sort_by]
    order_fn = asc if sort_dir == "asc" else desc
    query = query.order_by(order_fn(sort_column)).distinct()

    sales = query.offset((page - 1) * page_size).limit(page_size).all()

    return SaleListResponse(items=[_serialize_list_item(s) for s in sales], total=total)


@router.post("", response_model=SaleOut, status_code=status.HTTP_201_CREATED)
def create_sale(
    payload: SaleCreate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SALES_ROLES)),
):
    products_cache: dict = {}
    sale_items, total_amount = _build_items(db, company_id, payload.items, products_cache)

    invoice_number = _generate_invoice_number(db, company_id)

    customer = None
    customer_name = payload.customer_name
    if payload.customer_id:
        customer = db.query(Customer).filter(
            Customer.id == payload.customer_id, Customer.company_id == company_id
        ).first()
        if not customer:
            raise HTTPException(status_code=400, detail="Customer not found")
        customer_name = customer.full_name  # keep the snapshot in sync with the linked record

    sale = Sale(
        company_id=company_id,
        invoice_number=invoice_number,
        customer_name=customer_name,
        customer_id=customer.id if customer else None,
        sale_date=payload.sale_date or datetime.utcnow(),
        sales_channel=payload.sales_channel,
        payment_method=payload.payment_method,
        payment_status=payload.payment_status,
        notes=payload.notes,
        total_amount=total_amount,
        created_by=current_user.id,
    )
    db.add(sale)

    try:
        db.flush()
        for item in sale_items:
            item.sale_id = sale.id
            db.add(item)
            record_sale_stock_movement(db, item.product_id, company_id, -item.quantity, invoice_number, current_user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Invoice number collision, please retry")

    db.refresh(sale)

    if customer:
        recalculate_purchase_summary(db, customer.id)

    product_names = [p.name for p in products_cache.values()]
    log_action(db, request, "Sale Created", company_id=company_id, user_id=current_user.id,
               entity_name=f"{invoice_number} ({', '.join(product_names)})")
    db.commit()

    return db.query(Sale).options(
        joinedload(Sale.items).joinedload(SaleItem.product),
        joinedload(Sale.items).joinedload(SaleItem.category),
        joinedload(Sale.creator),
    ).filter(Sale.id == sale.id).first()


@router.get("/dashboard/summary", response_model=SalesDashboardSummary)
def get_sales_summary(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SALES_ROLES)),
):
    total_orders = db.query(func.count(Sale.id)).filter(Sale.company_id == company_id).scalar() or 0
    total_revenue = db.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(
        Sale.company_id == company_id
    ).scalar() or Decimal("0")
    total_units = db.query(func.coalesce(func.sum(SaleItem.quantity), 0)).join(
        Sale, SaleItem.sale_id == Sale.id
    ).filter(Sale.company_id == company_id).scalar() or 0

    avg_order_value = (total_revenue / total_orders) if total_orders > 0 else Decimal("0")

    return SalesDashboardSummary(
        total_sales=total_units,
        total_revenue=total_revenue,
        total_orders=total_orders,
        average_order_value=avg_order_value,
    )


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(
    sale_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SALES_ROLES)),
):
    sale = db.query(Sale).options(
        joinedload(Sale.items).joinedload(SaleItem.product),
        joinedload(Sale.items).joinedload(SaleItem.category),
        joinedload(Sale.creator),
    ).filter(Sale.id == sale_id, Sale.company_id == company_id).first()

    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    return sale


@router.get("/{sale_id}/export")
def export_invoice(
    sale_id: str,
    format: str = Query(..., pattern="^(csv|pdf)$"),
    request: Request = None,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SALES_ROLES)),
):
    sale = db.query(Sale).options(
        joinedload(Sale.items).joinedload(SaleItem.product),
        joinedload(Sale.items).joinedload(SaleItem.category),
        joinedload(Sale.creator),
    ).filter(Sale.id == sale_id, Sale.company_id == company_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    subtotal = sum((i.quantity * i.unit_price for i in sale.items), Decimal("0"))
    total_discount = sum((i.discount for i in sale.items), Decimal("0"))
    total_tax = sum((i.tax for i in sale.items), Decimal("0"))

    log_action(db, request, "Sale Exported", company_id=company_id, user_id=current_user.id,
               entity_name=sale.invoice_number, details=f"format={format}")

    if format == "csv":
        import csv, io
        from fastapi.responses import StreamingResponse
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Invoice", sale.invoice_number])
        writer.writerow(["Customer", sale.customer_name])
        writer.writerow(["Sale Date", sale.sale_date.strftime("%Y-%m-%d %H:%M")])
        writer.writerow(["Payment Method", sale.payment_method.value])
        writer.writerow(["Payment Status", sale.payment_status.value])
        writer.writerow(["Salesperson", sale.creator.name if sale.creator else ""])
        writer.writerow(["Notes", sale.notes or ""])
        writer.writerow([])
        writer.writerow(["Product", "SKU", "Category", "Quantity", "Unit Price", "Discount", "Tax", "Line Total"])
        for item in sale.items:
            writer.writerow([
                item.product.name, item.product.sku, item.category.name, item.quantity,
                str(item.unit_price), str(item.discount), str(item.tax), str(item.total),
            ])
        writer.writerow([])
        writer.writerow(["Subtotal", str(subtotal)])
        writer.writerow(["Discount", str(total_discount)])
        writer.writerow(["Tax", str(total_tax)])
        writer.writerow(["Grand Total", str(sale.total_amount)])
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=invoice_{sale.invoice_number}.csv"},
        )

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from fastapi.responses import StreamingResponse
        import io
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF export requires the 'reportlab' package.")

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(f"Invoice {sale.invoice_number}", styles["Title"]),
        Spacer(1, 0.3 * cm),
        Paragraph(
            f"Customer: {sale.customer_name} &nbsp;&nbsp; Date: {sale.sale_date.strftime('%Y-%m-%d')} &nbsp;&nbsp; "
            f"Payment: {sale.payment_method.value} ({sale.payment_status.value}) &nbsp;&nbsp; "
            f"Salesperson: {sale.creator.name if sale.creator else '—'}",
            styles["Normal"],
        ),
        Spacer(1, 0.5 * cm),
    ]

    item_rows = [["Product", "SKU", "Category", "Qty", "Unit Price", "Discount", "Tax", "Line Total"]] + [
        [item.product.name, item.product.sku, item.category.name, item.quantity,
         str(item.unit_price), str(item.discount), str(item.tax), str(item.total)]
        for item in sale.items
    ]
    item_table = Table(item_rows, repeatRows=1)
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elements += [item_table, Spacer(1, 0.6 * cm)]

    summary_rows = [
        ["Subtotal", str(subtotal)],
        ["Discount", str(total_discount)],
        ["Tax", str(total_tax)],
        ["Grand Total", str(sale.total_amount)],
    ]
    summary_table = Table(summary_rows, colWidths=[4 * cm, 4 * cm])
    summary_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
        ("LINEABOVE", (0, 3), (-1, 3), 0.6, colors.black),
    ]))
    elements.append(summary_table)
    if sale.notes:
        elements += [Spacer(1, 0.5 * cm), Paragraph(f"Notes: {sale.notes}", styles["Normal"])]

    doc.build(elements)
    pdf_buffer.seek(0)
    return StreamingResponse(
        pdf_buffer, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=invoice_{sale.invoice_number}.pdf"},
    )


@router.put("/{sale_id}", response_model=SaleOut)
def update_sale(
    sale_id: str,
    payload: SaleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SALES_ROLES)),
):
    sale = db.query(Sale).options(joinedload(Sale.items)).filter(
        Sale.id == sale_id, Sale.company_id == company_id
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    original_customer_id = sale.customer_id
    products_cache: dict = {}

    before_snapshot = {
        "customer_id": sale.customer_id, "customer_name": sale.customer_name,
        "sale_date": sale.sale_date, "sales_channel": sale.sales_channel,
        "payment_method": sale.payment_method, "payment_status": sale.payment_status,
        "notes": sale.notes, "total_amount": sale.total_amount,
    }

    if payload.items is not None:
        # Revert stock for the sale's current items before re-validating
        # the new set, so editing quantities on the same product works
        # correctly instead of comparing against already-reduced stock.
        for old_item in sale.items:
            product = db.query(Product).filter(Product.id == old_item.product_id).first()
            if product:
                product.stock_quantity += old_item.quantity
                products_cache[product.id] = product
                record_sale_stock_movement(db, old_item.product_id, company_id, old_item.quantity, sale.invoice_number, current_user.id)

        for old_item in list(sale.items):
            db.delete(old_item)
        db.flush()

        new_items, total_amount = _build_items(db, company_id, payload.items, products_cache)
        for item in new_items:
            item.sale_id = sale.id
            db.add(item)
            record_sale_stock_movement(db, item.product_id, company_id, -item.quantity, sale.invoice_number, current_user.id)
        sale.total_amount = total_amount

        log_action(db, request, "Inventory Updated", company_id=company_id,
                   user_id=current_user.id, entity_name=sale.invoice_number)

    if payload.clear_customer:
        sale.customer_id = None
        if payload.customer_name is not None:
            sale.customer_name = payload.customer_name
    elif payload.customer_id is not None:
        customer = db.query(Customer).filter(
            Customer.id == payload.customer_id, Customer.company_id == company_id
        ).first()
        if not customer:
            raise HTTPException(status_code=400, detail="Customer not found")
        sale.customer_id = customer.id
        sale.customer_name = customer.full_name
    elif payload.customer_name is not None:
        sale.customer_name = payload.customer_name
    if payload.sale_date is not None:
        sale.sale_date = payload.sale_date
    if payload.sales_channel is not None:
        sale.sales_channel = payload.sales_channel
    if payload.payment_method is not None:
        sale.payment_method = payload.payment_method
    if payload.payment_status is not None:
        sale.payment_status = payload.payment_status
    if payload.notes is not None:
        sale.notes = payload.notes

    db.commit()
    db.refresh(sale)

    affected_customer_ids = {cid for cid in (original_customer_id, sale.customer_id) if cid}
    for cid in affected_customer_ids:
        recalculate_purchase_summary(db, cid)

    after_snapshot = {
        "customer_id": sale.customer_id, "customer_name": sale.customer_name,
        "sale_date": sale.sale_date, "sales_channel": sale.sales_channel,
        "payment_method": sale.payment_method, "payment_status": sale.payment_status,
        "notes": sale.notes, "total_amount": sale.total_amount,
    }
    log_action(db, request, "Sale Updated", company_id=company_id,
               user_id=current_user.id, entity_name=sale.invoice_number,
               resource_type="Sale", resource_id=sale.id,
               before=before_snapshot, after=after_snapshot)
    db.commit()

    return db.query(Sale).options(
        joinedload(Sale.items).joinedload(SaleItem.product),
        joinedload(Sale.items).joinedload(SaleItem.category),
        joinedload(Sale.creator),
    ).filter(Sale.id == sale.id).first()


@router.delete("/{sale_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sale(
    sale_id: str,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(require_roles(SALES_ROLES)),
):
    sale = db.query(Sale).options(joinedload(Sale.items)).filter(
        Sale.id == sale_id, Sale.company_id == company_id
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    products_cache: dict = {}
    invoice_number = sale.invoice_number
    linked_customer_id = sale.customer_id
    for item in sale.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            product.stock_quantity += item.quantity
            products_cache[product.id] = product
            record_sale_stock_movement(db, item.product_id, company_id, item.quantity, invoice_number, current_user.id)

    db.delete(sale)
    db.commit()

    if linked_customer_id:
        recalculate_purchase_summary(db, linked_customer_id)

    log_action(db, request, "Sale Deleted", company_id=company_id,
               user_id=current_user.id, entity_name=invoice_number)
    if products_cache:
        log_action(db, request, "Inventory Updated", company_id=company_id,
                   user_id=current_user.id, entity_name=invoice_number)
    db.commit()

    return None
