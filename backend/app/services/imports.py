"""
Data Import & Integration Management (Task 12).

Pipeline implemented here:

    File Upload -> Parse CSV -> Column Validation -> Row Validation
    -> Duplicate Detection -> Preview / Validation Result
    -> (Admin confirms) -> Process Valid Records -> Insert Into Database
    -> Import Result -> Import History

Data-integrity approach (documented per the task's requirement to explain
the chosen strategy):
  * Each row is processed inside its own SAVEPOINT (`db.begin_nested()`).
    A failure on one row rolls back only that row's partial writes and
    the loop continues — so one bad row can never corrupt or discard the
    rows around it (partial-success batch processing).
  * The parent transaction is committed once at the end of processing.
    If something catastrophic happens before that commit (e.g. the DB
    connection drops), nothing in the batch is persisted, since nothing
    was committed yet — so the job is never left half-applied at the
    top level either.
  * The staged CSV text lives on the ImportJob row itself, so upload,
    validate, and process are separate HTTP calls without needing a
    server-side file cache.
"""
import csv
import io
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    ImportType, ImportRowStatus,
    Product, Category, ProductStatus, CategoryStatus,
    Customer, CustomerPurchaseSummary, CustomerType, CustomerStatus, CustomerActivityType,
    Sale, SaleItem, SalesChannel, PaymentMethod, PaymentStatus,
)
from app.models.inventory import Inventory, InventoryMovement, MovementType
from app.services.notifications import evaluate_product_stock_alert
from app.schemas.inventory_utils import DEFAULT_REORDER_LEVEL
from app.services.customers import generate_customer_code, log_customer_activity, recalculate_purchase_summary

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\s\-().]{6,19}$")

DATE_FORMATS = [
    "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d",
    "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
]

# Canonical display name -> normalized key used for header matching.
REQUIRED_COLUMNS = {
    ImportType.PRODUCTS: ["Product Name", "SKU", "Category", "Unit Price", "Stock Quantity"],
    ImportType.INVENTORY: ["SKU", "Stock Quantity", "Reason"],
    ImportType.CUSTOMERS: ["Name", "Email", "Phone"],
    ImportType.SALES: ["Customer", "Product", "Quantity", "Unit Price", "Sale Date"],
}

OPTIONAL_COLUMNS = {
    ImportType.PRODUCTS: ["Brand", "Description", "Cost Price", "Unit of Measure"],
    ImportType.INVENTORY: ["Reorder Level", "Remarks"],
    ImportType.CUSTOMERS: ["Address", "City", "State", "Country", "Postal Code", "Customer Type"],
    ImportType.SALES: ["Invoice Number", "Sales Channel", "Payment Method"],
}


def _normalize(header: str) -> str:
    return re.sub(r"[\s_]+", "_", header.strip().lower())


class ParsedCSV:
    def __init__(self, fieldnames: list[str], rows: list[dict]):
        self.fieldnames = fieldnames
        self.rows = rows  # each row: {original_header: value}


def parse_csv_text(text: str) -> ParsedCSV:
    # csv module handles \r\n and quoted fields; strip a UTF-8 BOM if present.
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [f.strip() for f in (reader.fieldnames or [])]
    rows = []
    for raw_row in reader:
        # Re-key with stripped header names; DictReader keeps original keys.
        row = {}
        for key, value in raw_row.items():
            if key is None:
                continue
            row[key.strip()] = (value or "").strip()
        rows.append(row)
    return ParsedCSV(fieldnames, rows)


def missing_required_columns(import_type: ImportType, fieldnames: list[str]) -> list[str]:
    normalized_present = {_normalize(f) for f in fieldnames}
    missing = []
    for display_name in REQUIRED_COLUMNS[import_type]:
        if _normalize(display_name) not in normalized_present:
            missing.append(display_name)
    return missing


def header_map(fieldnames: list[str]) -> dict:
    """normalized_key -> original header actually present in the file"""
    return {_normalize(f): f for f in fieldnames}


_header_map = header_map  # internal alias used elsewhere in this module


def _get(row: dict, header_map: dict, display_name: str) -> str:
    original = header_map.get(_normalize(display_name))
    if original is None:
        return ""
    return (row.get(original) or "").strip()


def _parse_decimal(value: str) -> Optional[Decimal]:
    try:
        cleaned = value.replace(",", "").replace("₹", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, AttributeError):
        return None


def _parse_int(value: str) -> Optional[int]:
    try:
        return int(Decimal(value.replace(",", "").strip()))
    except (InvalidOperation, AttributeError, ValueError):
        return None


def _parse_date(value: str) -> Optional[datetime]:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


class RowResult:
    __slots__ = ("row_number", "data", "status", "message")

    def __init__(self, row_number: int, data: dict, status: Optional[ImportRowStatus], message: str = ""):
        self.row_number = row_number
        self.data = data
        self.status = status  # None means VALID
        self.message = message


def validate_rows(db: Session, company_id: str, import_type: ImportType, parsed: ParsedCSV) -> list[RowResult]:
    header_map = _header_map(parsed.fieldnames)

    if import_type == ImportType.PRODUCTS:
        return _validate_product_rows(db, company_id, parsed.rows, header_map)

    if import_type == ImportType.INVENTORY:
        return _validate_inventory_rows(db, company_id, parsed.rows, header_map)

    if import_type == ImportType.CUSTOMERS:
        return _validate_customer_rows(db, company_id, parsed.rows, header_map)

    if import_type == ImportType.SALES:
        return _validate_sale_rows(db, company_id, parsed.rows, header_map)

    raise ValueError(f"Unsupported import type: {import_type}")


# ---------------------------------------------------------------- PRODUCTS

def _validate_product_rows(db: Session, company_id: str, rows: list[dict], header_map: dict) -> list[RowResult]:
    existing_skus = {
        sku.lower() for (sku,) in db.query(Product.sku).filter(Product.company_id == company_id).all()
    }
    seen_skus: set[str] = set()
    results = []

    for i, row in enumerate(rows, start=1):
        name = _get(row, header_map, "Product Name")
        sku = _get(row, header_map, "SKU")
        category = _get(row, header_map, "Category")
        price_raw = _get(row, header_map, "Unit Price")
        stock_raw = _get(row, header_map, "Stock Quantity")

        problems = []
        if not name:
            problems.append("Product Name is required")
        if not sku:
            problems.append("SKU is required")
        if not category:
            problems.append("Category is required")

        price = _parse_decimal(price_raw)
        if price is None or price <= 0:
            problems.append("Unit Price must be a number greater than zero")

        stock = _parse_int(stock_raw)
        if stock is None or stock < 0:
            problems.append("Stock Quantity must be a non-negative whole number")

        if problems:
            results.append(RowResult(i, row, ImportRowStatus.INVALID, "; ".join(problems)))
            continue

        if sku.lower() in existing_skus or sku.lower() in seen_skus:
            results.append(RowResult(i, row, ImportRowStatus.DUPLICATE, f"Duplicate SKU: {sku}"))
            continue

        seen_skus.add(sku.lower())
        results.append(RowResult(i, row, None))

    return results

# ---------------------------------------------------------------- INVENTORY

def _validate_inventory_rows(
    db: Session,
    company_id: str,
    rows: list[dict],
    header_map: dict,
) -> list[RowResult]:

    products = db.query(Product).filter(
        Product.company_id == company_id
    ).all()

    products_by_sku = {
        product.sku.lower(): product
        for product in products
    }

    inventories = db.query(Inventory).filter(
        Inventory.company_id == company_id
    ).all()

    inventory_by_product = {
        inventory.product_id: inventory
        for inventory in inventories
    }

    seen_skus: set[str] = set()
    results = []

    def parse_whole_number(value: str) -> Optional[int]:
        try:
            number = Decimal(value.replace(",", "").strip())

            if not number.is_finite() or number < 0:
                return None

            if number != number.to_integral_value():
                return None

            return int(number)
        except (InvalidOperation, AttributeError, ValueError):
            return None

    for i, row in enumerate(rows, start=1):
        sku = _get(row, header_map, "SKU")
        stock_raw = _get(row, header_map, "Stock Quantity")
        reorder_raw = _get(row, header_map, "Reorder Level")
        reason = _get(row, header_map, "Reason")
        remarks = _get(row, header_map, "Remarks")

        problems = []

        if not sku:
            problems.append("SKU is required")

        stock = parse_whole_number(stock_raw)

        if stock is None:
            problems.append(
                "Stock Quantity must be a non-negative whole number"
            )

        reorder_level = None

        if reorder_raw:
            reorder_level = parse_whole_number(reorder_raw)

            if reorder_level is None:
                problems.append(
                    "Reorder Level must be a non-negative whole number"
                )

        if not reason:
            problems.append("Reason is required")
        elif len(reason) > 255:
            problems.append("Reason cannot exceed 255 characters")

        if len(remarks) > 1000:
            problems.append("Remarks cannot exceed 1000 characters")

        if problems:
            results.append(
                RowResult(i, row, ImportRowStatus.INVALID, "; ".join(problems))
            )
            continue

        sku_lower = sku.lower()

        if sku_lower in seen_skus:
            results.append(
                RowResult(i, row, ImportRowStatus.DUPLICATE, f"Duplicate SKU in file: {sku}")
            )
            continue

        seen_skus.add(sku_lower)

        product = products_by_sku.get(sku_lower)

        if not product:
            results.append(
                RowResult(i, row, ImportRowStatus.INVALID, f"Product not found for SKU: {sku}")
            )
            continue

        inventory = inventory_by_product.get(product.id)

        if not inventory:
            results.append(
                RowResult(i, row, ImportRowStatus.INVALID, f"Inventory record not found for SKU: {sku}")
            )
            continue

        if stock < inventory.reserved_stock:
            results.append(
                RowResult(
                    i,
                    row,
                    ImportRowStatus.INVALID,
                    f"Target stock ({stock}) cannot be below reserved stock ({inventory.reserved_stock})",
                )
            )
            continue

        results.append(RowResult(i, row, None))

    return results

# ---------------------------------------------------------------- INVENTORY PROCESSING

def process_inventory_row(
    db: Session,
    company_id: str,
    row: dict,
    header_map: dict,
    performed_by: str,
) -> Inventory:

    sku = _get(row, header_map, "SKU")
    stock_raw = _get(row, header_map, "Stock Quantity")
    reorder_raw = _get(row, header_map, "Reorder Level")
    reason = _get(row, header_map, "Reason")
    remarks = _get(row, header_map, "Remarks") or None

    # Resolve product within the authenticated company.
    product = db.query(Product).filter(
        Product.company_id == company_id,
        Product.sku.ilike(sku),
    ).first()

    if not product:
        raise ValueError(f"Product not found for SKU: {sku}")

    # Lock inventory row to prevent concurrent stock updates.
    inventory = db.query(Inventory).filter(
        Inventory.company_id == company_id,
        Inventory.product_id == product.id,
    ).with_for_update().first()

    if not inventory:
        raise ValueError(f"Inventory record not found for SKU: {sku}")

    # Parse target stock quantity.
    try:
        stock_decimal = Decimal(stock_raw.replace(",", "").strip())

        if (
            not stock_decimal.is_finite()
            or stock_decimal < 0
            or stock_decimal != stock_decimal.to_integral_value()
        ):
            raise ValueError

        target_stock = int(stock_decimal)

    except (InvalidOperation, AttributeError, ValueError):
        raise ValueError("Stock Quantity must be a non-negative whole number")

    # Validate reserved stock again immediately before processing.
    if target_stock < inventory.reserved_stock:
        raise ValueError(
            f"Target stock ({target_stock}) cannot be below "
            f"reserved stock ({inventory.reserved_stock})"
        )

    # Validate optional reorder level.
    new_reorder_level = inventory.reorder_level

    if reorder_raw:
        try:
            reorder_decimal = Decimal(reorder_raw.replace(",", "").strip())

            if (
                not reorder_decimal.is_finite()
                or reorder_decimal < 0
                or reorder_decimal != reorder_decimal.to_integral_value()
            ):
                raise ValueError

            new_reorder_level = int(reorder_decimal)

        except (InvalidOperation, AttributeError, ValueError):
            raise ValueError("Reorder Level must be a non-negative whole number")

    if not reason or len(reason) > 255:
        raise ValueError("Reason is required and cannot exceed 255 characters")

    if remarks and len(remarks) > 1000:
        raise ValueError("Remarks cannot exceed 1000 characters")

    previous_stock = inventory.current_stock
    previous_reorder_level = inventory.reorder_level

    delta = target_stock - previous_stock

    # Update inventory and product catalog together.
    inventory.current_stock = target_stock
    inventory.reorder_level = new_reorder_level

    inventory.update_status()

    product.stock_quantity = target_stock

    # Record stock movement only when the quantity changes.
    if delta != 0:
        movement_type = (
            MovementType.STOCK_ADDITION
            if delta > 0
            else MovementType.STOCK_REMOVAL
        )

        movement = InventoryMovement(
            inventory_id=inventory.id,
            movement_type=movement_type,
            quantity_changed=delta,
            previous_quantity=previous_stock,
            updated_quantity=target_stock,
            reason=reason,
            remarks=remarks,
            performed_by=performed_by,
        )

        db.add(movement)

    # Re-evaluate alerts after stock or reorder-level changes.
    if delta != 0 or new_reorder_level != previous_reorder_level:
        evaluate_product_stock_alert(
            db,
            company_id,
            inventory,
            product,
        )

    db.flush()

    return inventory

# ---------------------------------------------------------------- CUSTOMERS

def _validate_customer_rows(db: Session, company_id: str, rows: list[dict], header_map: dict) -> list[RowResult]:
    existing_emails = {
        e.lower() for (e,) in db.query(Customer.email).filter(
            Customer.company_id == company_id, Customer.is_deleted.is_(False)
        ).all()
    }
    existing_phones = {
        p for (p,) in db.query(Customer.phone).filter(
            Customer.company_id == company_id, Customer.is_deleted.is_(False)
        ).all()
    }
    seen_emails: set[str] = set()
    seen_phones: set[str] = set()
    results = []

    for i, row in enumerate(rows, start=1):
        name = _get(row, header_map, "Name")
        email = _get(row, header_map, "Email")
        phone = _get(row, header_map, "Phone")

        problems = []
        if not name:
            problems.append("Name is required")
        if not email:
            problems.append("Email is required")
        elif not EMAIL_PATTERN.match(email):
            problems.append("Email is not valid")
        if not phone:
            problems.append("Phone is required")
        elif not PHONE_PATTERN.match(phone):
            problems.append("Phone is not valid")

        if problems:
            results.append(RowResult(i, row, ImportRowStatus.INVALID, "; ".join(problems)))
            continue

        email_l = email.lower()
        if email_l in existing_emails or email_l in seen_emails or phone in existing_phones or phone in seen_phones:
            field = "email" if (email_l in existing_emails or email_l in seen_emails) else "phone"
            results.append(RowResult(i, row, ImportRowStatus.DUPLICATE, f"Duplicate {field}: {email if field == 'email' else phone}"))
            continue

        seen_emails.add(email_l)
        seen_phones.add(phone)
        results.append(RowResult(i, row, None))

    return results


# ---------------------------------------------------------------- SALES

def _parse_sales_channel(value: str) -> SalesChannel:
    raw = (value or "").strip().upper()
    normalized = raw.replace("-", "_").replace(" ", "_")

    channel_map = {
        "RETAIL": SalesChannel.RETAIL_STORE,
        "RETAIL_STORE": SalesChannel.RETAIL_STORE,
        "ONLINE": SalesChannel.ONLINE_STORE,
        "ONLINE_STORE": SalesChannel.ONLINE_STORE,
        "MARKETPLACE": SalesChannel.MARKETPLACE,
    }

    if not normalized:
        return SalesChannel.RETAIL_STORE

    if normalized not in channel_map:
        raise ValueError(
            f"Unsupported Sales Channel: {value}. "
            "Allowed values: Retail Store, Online, Marketplace"
        )

    return channel_map[normalized]

def _validate_sale_rows(db: Session, company_id: str, rows: list[dict], header_map: dict) -> list[RowResult]:
    products = db.query(Product).filter(Product.company_id == company_id).all()
    products_by_sku = {p.sku.lower(): p for p in products}
    products_by_name = {p.name.lower(): p for p in products}

    customers = db.query(Customer).filter(
        Customer.company_id == company_id, Customer.is_deleted.is_(False)
    ).all()
    customers_by_name = {c.full_name.lower(): c for c in customers}
    customers_by_email = {c.email.lower(): c for c in customers}

    existing_invoices = {
        inv.lower() for (inv,) in db.query(Sale.invoice_number).filter(Sale.company_id == company_id).all()
    }
    seen_invoices: set[str] = set()

    # Tracks stock as it would be consumed row-by-row within this file,
    # so two rows selling the same product can't both "pass" against the
    # same starting stock figure.
    remaining_stock = {p.id: p.stock_quantity for p in products}

    results = []
    for i, row in enumerate(rows, start=1):
        customer_ref = _get(row, header_map, "Customer")
        product_ref = _get(row, header_map, "Product")
        qty_raw = _get(row, header_map, "Quantity")
        price_raw = _get(row, header_map, "Unit Price")
        date_raw = _get(row, header_map, "Sale Date")
        invoice_raw = _get(row, header_map, "Invoice Number")

        # Validate Sales Channel
        channel_raw = _get(row, header_map, "Sales Channel")

        problems = []

        try:
            _parse_sales_channel(channel_raw)
        except ValueError as exc:
            problems.append(str(exc))

        if not customer_ref:
            problems.append("Customer is required")
        if not product_ref:
            problems.append("Product is required")

        qty = _parse_int(qty_raw)
        if qty is None or qty <= 0:
            problems.append("Quantity must be a whole number greater than zero")

        price = _parse_decimal(price_raw)
        if price is None or price < 0:
            problems.append("Unit Price must be a non-negative number")

        sale_date = _parse_date(date_raw) if date_raw else None
        if not date_raw:
            problems.append("Sale Date is required")
        elif sale_date is None:
            problems.append(f"Sale Date '{date_raw}' is not a recognizable date")

        customer = customers_by_name.get(customer_ref.lower()) or customers_by_email.get(customer_ref.lower())
        if customer_ref and not customer:
            problems.append(f"Customer not found: {customer_ref}")

        product = products_by_sku.get(product_ref.lower()) or products_by_name.get(product_ref.lower())
        if product_ref and not product:
            problems.append(f"Product not found: {product_ref}")
        elif product and product.status != ProductStatus.ACTIVE:
            problems.append(f"Product is inactive: {product_ref}")

        if product and qty is not None and qty > 0:
            avail = remaining_stock.get(product.id, 0)
            if qty > avail:
                problems.append(f"Quantity ({qty}) exceeds available stock ({avail}) for '{product.name}'")

        if problems:
            results.append(RowResult(i, row, ImportRowStatus.INVALID, "; ".join(problems)))
            continue

        if invoice_raw:
            inv_l = invoice_raw.lower()
            if inv_l in existing_invoices or inv_l in seen_invoices:
                results.append(RowResult(i, row, ImportRowStatus.DUPLICATE, f"Duplicate Invoice Number: {invoice_raw}"))
                continue
            seen_invoices.add(inv_l)

        remaining_stock[product.id] = remaining_stock.get(product.id, 0) - qty
        results.append(RowResult(i, row, None))

    return results


# =========================================================================
# PROCESSING — turns a VALID RowResult into real database rows.
# Each function returns the created object; raises ValueError on failure
# (caller wraps this in a per-row SAVEPOINT and records it as FAILED).
# =========================================================================

def process_product_row(db: Session, company_id: str, row: dict, header_map: dict) -> Product:
    name = _get(row, header_map, "Product Name")
    sku = _get(row, header_map, "SKU")
    category_name = _get(row, header_map, "Category")
    brand = _get(row, header_map, "Brand") or None
    description = _get(row, header_map, "Description") or None
    unit_price = _parse_decimal(_get(row, header_map, "Unit Price"))
    stock_quantity = _parse_int(_get(row, header_map, "Stock Quantity")) or 0
    cost_price_raw = _get(row, header_map, "Cost Price")
    cost_price = _parse_decimal(cost_price_raw) if cost_price_raw else None
    if cost_price is None:
        cost_price = unit_price  # sensible default: no data loss, satisfies cost <= price
    uom = _get(row, header_map, "Unit of Measure") or "unit"

    category = db.query(Category).filter(
        Category.company_id == company_id, Category.name.ilike(category_name)
    ).first()
    if not category:
        category = Category(company_id=company_id, name=category_name, status=CategoryStatus.ACTIVE)
        db.add(category)
        db.flush()

    # Re-check for a race against another row/import processed since validation.
    dup = db.query(Product.id).filter(
        Product.company_id == company_id, Product.sku.ilike(sku)
    ).first()
    if dup:
        raise ValueError(f"Duplicate SKU: {sku}")

    product = Product(
        company_id=company_id,
        category_id=category.id,
        name=name,
        sku=sku,
        brand=brand,
        description=description,
        unit_price=unit_price,
        cost_price=cost_price,
        stock_quantity=stock_quantity,
        unit_of_measure=uom,
        status=ProductStatus.ACTIVE,
    )
    db.add(product)
    db.flush()

    inv = Inventory(
        company_id=company_id,
        product_id=product.id,
        current_stock=stock_quantity,
        reserved_stock=0,
        reorder_level=DEFAULT_REORDER_LEVEL,
    )
    inv.update_status()
    db.add(inv)
    return product


def process_customer_row(db: Session, company_id: str, row: dict, header_map: dict, created_by: Optional[str]) -> Customer:
    full_name = _get(row, header_map, "Name")
    parts = full_name.split(" ", 1)
    first_name, last_name = (parts[0], parts[1] if len(parts) > 1 else "")
    email = _get(row, header_map, "Email")
    phone = _get(row, header_map, "Phone")
    address = _get(row, header_map, "Address") or None
    city = _get(row, header_map, "City") or None
    state = _get(row, header_map, "State") or None
    country = _get(row, header_map, "Country") or None
    postal_code = _get(row, header_map, "Postal Code") or None
    customer_type_raw = _get(row, header_map, "Customer Type").upper() or "RETAIL"
    try:
        customer_type = CustomerType(customer_type_raw)
    except ValueError:
        customer_type = CustomerType.RETAIL

    dup = db.query(Customer.id).filter(
        Customer.company_id == company_id, Customer.is_deleted.is_(False),
        (Customer.email.ilike(email)) | (Customer.phone == phone),
    ).first()
    if dup:
        raise ValueError(f"A customer with this email or phone already exists: {email} / {phone}")

    customer = Customer(
        company_id=company_id,
        customer_code=generate_customer_code(db, company_id),
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        email=email,
        phone=phone,
        address=address,
        city=city,
        state=state,
        country=country,
        postal_code=postal_code,
        customer_type=customer_type,
        status=CustomerStatus.ACTIVE,
        created_by=created_by,
    )
    db.add(customer)
    db.flush()

    db.add(CustomerPurchaseSummary(customer_id=customer.id, company_id=company_id))
    log_customer_activity(
        db, customer.id, company_id, CustomerActivityType.REGISTERED,
        f"Registered as a {customer_type.value.title()} customer (via CSV import).",
    )
    return customer


def process_sale_row(db: Session, company_id: str, row: dict, header_map: dict, created_by: str) -> Sale:
    from app.routers.sales import _generate_invoice_number, record_sale_stock_movement

    customer_ref = _get(row, header_map, "Customer")
    product_ref = _get(row, header_map, "Product")
    qty = _parse_int(_get(row, header_map, "Quantity"))
    unit_price = _parse_decimal(_get(row, header_map, "Unit Price"))
    sale_date = _parse_date(_get(row, header_map, "Sale Date")) or datetime.utcnow()
    invoice_raw = _get(row, header_map, "Invoice Number")
    channel_raw = _get(row, header_map, "Sales Channel")
    payment_raw = _get(row, header_map, "Payment Method").upper()

    sales_channel = _parse_sales_channel(channel_raw)
    try:
        payment_method = PaymentMethod(payment_raw) if payment_raw else PaymentMethod.CASH
    except ValueError:
        payment_method = PaymentMethod.CASH

    customer = db.query(Customer).filter(
        Customer.company_id == company_id, Customer.is_deleted.is_(False),
        (Customer.full_name.ilike(customer_ref)) | (Customer.email.ilike(customer_ref)),
    ).first()
    if not customer:
        raise ValueError(f"Customer not found: {customer_ref}")

    product = db.query(Product).filter(
        Product.company_id == company_id,
        (Product.sku.ilike(product_ref)) | (Product.name.ilike(product_ref)),
    ).first()
    if not product:
        raise ValueError(f"Product not found: {product_ref}")
    if product.status != ProductStatus.ACTIVE:
        raise ValueError(f"Product is inactive: {product_ref}")
    if qty > product.stock_quantity:
        raise ValueError(f"Insufficient stock for '{product.name}'. Available: {product.stock_quantity}")

    invoice_number = invoice_raw or _generate_invoice_number(db, company_id)
    dup = db.query(Sale.id).filter(
        Sale.company_id == company_id, Sale.invoice_number.ilike(invoice_number)
    ).first()
    if dup:
        raise ValueError(f"Duplicate Invoice Number: {invoice_number}")

    line_total = (unit_price or product.unit_price) * qty
    sale = Sale(
        company_id=company_id,
        invoice_number=invoice_number,
        customer_name=customer.full_name,
        customer_id=customer.id,
        sale_date=sale_date,
        sales_channel=sales_channel,
        payment_method=payment_method,
        payment_status=PaymentStatus.PAID,
        total_amount=line_total,
        created_by=created_by,
    )
    db.add(sale)
    db.flush()

    product.stock_quantity -= qty
    item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        category_id=product.category_id,
        quantity=qty,
        unit_price=unit_price or product.unit_price,
        discount=0,
        tax=0,
        total=line_total,
    )
    db.add(item)
    record_sale_stock_movement(db, product.id, company_id, -qty, invoice_number, created_by)

    return sale
