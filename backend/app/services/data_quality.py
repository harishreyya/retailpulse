
import json
from collections import defaultdict
from datetime import datetime
from app.models import (
    Product,
    ProductStatus,
    Customer,
    CustomerPurchaseSummary,
    Category,
    DataQualityIssue,
    DataQualityIssueEvent,
    ReconciliationRun,
    Sale,
    SaleItem,
    Inventory,
    InventoryMovement,
)
from decimal import Decimal
from sqlalchemy import func

def _normalise_text(value):
    """Trim text and return an empty string for missing values."""
    return (value or "").strip()


def _issue_fingerprint(issue_type, record_type, record_id):
    """Build a stable key so repeated runs don't create duplicate issues."""
    return f"{issue_type}:{record_type}:{record_id}"

def _record_key(record_type, record_id):
    """Build a unique key for a record across reconciliation checks."""
    return (record_type, str(record_id))

def _upsert_issue(
    db,
    company_id,
    issue_type,
    severity,
    module,
    record_type,
    record_id,
    record_label,
    description,
    details,
):
    """
    Create a new issue or refresh the existing issue for this company.

    Existing RESOLVED or IGNORED issues are reopened if the same problem
    is detected again.
    """
    fingerprint = _issue_fingerprint(issue_type, record_type, record_id)

    issue = (
        db.query(DataQualityIssue)
        .filter(
            DataQualityIssue.company_id == company_id,
            DataQualityIssue.fingerprint == fingerprint,
        )
        .one_or_none()
    )

    if issue is None:
        issue = DataQualityIssue(
            company_id=company_id,
            fingerprint=fingerprint,
            issue_type=issue_type,
            severity=severity,
            module=module,
            record_type=record_type,
            record_id=str(record_id) if record_id is not None else None,
            record_label=record_label,
            description=description,
            details_json=json.dumps(details, default=str),
            status="OPEN",
        )
        db.add(issue)
    else:
        issue.severity = severity
        issue.module = module
        issue.record_label = record_label
        issue.description = description
        issue.details_json = json.dumps(details, default=str)
        issue.last_detected_at = datetime.utcnow()

        if issue.status in ("RESOLVED", "IGNORED"):
            issue.status = "OPEN"
            issue.resolved_at = None
            issue.resolved_by = None
            issue.resolution_note = None

    return issue




def check_products(db, company_id):
    """Find products with missing required values and duplicate normalised SKUs."""
    records_checked = 0
    issues_detected = 0
    checked_record_keys = set()
    issue_record_keys = set()

    products = (
        db.query(Product)
        .filter(Product.company_id == company_id)
        .all()
    )

    sku_groups = defaultdict(list)

    for product in products:
        records_checked += 1

        checked_record_keys.add(
            _record_key("PRODUCT", product.id)
        )

        missing_fields = []

        if not _normalise_text(product.name):
            missing_fields.append("name")

        if not _normalise_text(product.sku):
            missing_fields.append("sku")

        if not _normalise_text(product.unit_of_measure):
            missing_fields.append("unit_of_measure")

        if product.unit_price is None:
            missing_fields.append("unit_price")

        if product.cost_price is None:
            missing_fields.append("cost_price")

        if product.category_id is None:
            missing_fields.append("category_id")

        if missing_fields:
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="PRODUCT_REQUIRED_FIELD_MISSING",
                severity="ERROR",
                module="PRODUCTS",
                record_type="PRODUCT",
                record_id=product.id,
                record_label=product.name or product.sku or str(product.id),
                description="Product is missing one or more required values.",
                details={"missing_fields": missing_fields},
            )
            issues_detected += 1

            issue_record_keys.add(
                _record_key("PRODUCT", product.id)
            )

        normalized_sku = _normalise_text(product.sku).casefold()

        if normalized_sku:
            sku_groups[normalized_sku].append(product)

    for normalized_sku, matching_products in sku_groups.items():
        if len(matching_products) < 2:
            continue

        product_ids = sorted(
            str(product.id) for product in matching_products
        )

        for product in matching_products:
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="PRODUCT_DUPLICATE_SKU",
                severity="ERROR",
                module="PRODUCTS",
                record_type="PRODUCT",
                record_id=product.id,
                record_label=product.name or product.sku,
                description=f"SKU '{normalized_sku}' is shared by multiple products after normalisation.",
                details={
                    "normalised_sku": normalized_sku,
                    "matching_product_ids": product_ids,
                },
            )
            issues_detected += 1

            issue_record_keys.add(
                _record_key("PRODUCT", product.id)
            )

    return {
        "records_checked": records_checked,
        "issues_detected": issues_detected,
        "checked_record_keys": checked_record_keys,
        "issue_record_keys": issue_record_keys,
    }

def check_customers(db, company_id):
    """Find active records with missing required customer values."""
    records_checked = 0
    issues_detected = 0
    checked_record_keys = set()
    issue_record_keys = set()

    customers = (
        db.query(Customer)
        .filter(
            Customer.company_id == company_id,
            Customer.is_deleted.is_(False),
        )
        .all()
    )

    for customer in customers:
        records_checked += 1

        checked_record_keys.add(
            _record_key("CUSTOMER", customer.id)
        )

        missing_fields = []

        if not _normalise_text(customer.customer_code):
            missing_fields.append("customer_code")

        if not _normalise_text(customer.first_name):
            missing_fields.append("first_name")

        if not _normalise_text(customer.full_name):
            missing_fields.append("full_name")

        if not _normalise_text(customer.email):
            missing_fields.append("email")

        if not _normalise_text(customer.phone):
            missing_fields.append("phone")

        if missing_fields:
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="CUSTOMER_REQUIRED_FIELD_MISSING",
                severity="ERROR",
                module="CUSTOMERS",
                record_type="CUSTOMER",
                record_id=customer.id,
                record_label=customer.full_name or customer.customer_code,
                description="Customer is missing one or more required values.",
                details={"missing_fields": missing_fields},
            )

            issues_detected += 1

            issue_record_keys.add(
                _record_key("CUSTOMER", customer.id)
            )

    return {
        "records_checked": records_checked,
        "issues_detected": issues_detected,
        "checked_record_keys": checked_record_keys,
        "issue_record_keys": issue_record_keys,
    }

def check_customer_purchase_summaries(db, company_id):
    """Reconcile stored customer purchase summaries with sales transactions."""
    records_checked = 0
    issues_detected = 0
    checked_record_keys = set()
    issue_record_keys = set()

    summaries = (
        db.query(CustomerPurchaseSummary)
        .join(Customer, Customer.id == CustomerPurchaseSummary.customer_id)
        .filter(
            Customer.company_id == company_id,
            CustomerPurchaseSummary.company_id == company_id,
        )
        .all()
    )

    for summary in summaries:
        customer = (
            db.query(Customer)
            .filter(
                Customer.id == summary.customer_id,
                Customer.company_id == company_id,
            )
            .first()
        )

        if customer is None:
            continue

        records_checked += 1

        checked_record_keys.add(
            _record_key("CUSTOMER", customer.id)
        )

        # Aggregate sales separately so each sale's revenue is counted once.
        sales_aggregate = (
            db.query(
                func.count(Sale.id),
                func.coalesce(func.sum(Sale.total_amount), 0),
            )
            .filter(
                Sale.customer_id == customer.id,
                Sale.company_id == company_id,
            )
            .first()
        )

        # Aggregate quantities from sale items independently.
        expected_quantity = (
            db.query(func.coalesce(func.sum(SaleItem.quantity), 0))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .filter(
                Sale.customer_id == customer.id,
                Sale.company_id == company_id,
            )
            .scalar()
        ) or 0

        expected_orders = int(sales_aggregate[0] or 0)

        expected_revenue = Decimal(
            str(sales_aggregate[1] or 0)
        ).quantize(Decimal("0.01"))

        expected_quantity = int(expected_quantity)

        expected_average = (
            (expected_revenue / expected_orders).quantize(Decimal("0.01"))
            if expected_orders
            else Decimal("0.00")
        )

        stored_revenue = Decimal(
            str(summary.total_revenue)
        ).quantize(Decimal("0.01"))

        stored_average = Decimal(
            str(summary.average_order_value)
        ).quantize(Decimal("0.01"))

        mismatches = {}

        if summary.total_orders != expected_orders:
            mismatches["total_orders"] = {
                "stored": summary.total_orders,
                "expected": expected_orders,
            }

        if stored_revenue != expected_revenue:
            mismatches["total_revenue"] = {
                "stored": str(stored_revenue),
                "expected": str(expected_revenue),
            }

        if summary.total_quantity != expected_quantity:
            mismatches["total_quantity"] = {
                "stored": summary.total_quantity,
                "expected": expected_quantity,
            }

        if stored_average != expected_average:
            mismatches["average_order_value"] = {
                "stored": str(stored_average),
                "expected": str(expected_average),
            }

        if mismatches:
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="CUSTOMER_PURCHASE_SUMMARY_MISMATCH",
                severity="WARNING",
                module="CUSTOMERS",
                record_type="CUSTOMER",
                record_id=customer.id,
                record_label=customer.full_name or customer.customer_code,
                description=(
                    "Stored customer purchase summary does not match "
                    "the customer's sales transactions."
                ),
                details={
                    "customer_id": str(customer.id),
                    "mismatches": mismatches,
                },
            )

            issues_detected += 1

            issue_record_keys.add(
                _record_key("CUSTOMER", customer.id)
            )

    return {
        "records_checked": records_checked,
        "issues_detected": issues_detected,
        "checked_record_keys": checked_record_keys,
        "issue_record_keys": issue_record_keys,
    }

def check_inventory(db, company_id):
    """Find inconsistencies in inventory quantities and stock movements."""
    records_checked = 0
    issues_detected = 0
    checked_record_keys = set()
    issue_record_keys = set()

    inventories = (
        db.query(Inventory)
        .filter(Inventory.company_id == company_id)
        .all()
    )

    for inventory in inventories:
        records_checked += 1

        checked_record_keys.add(
            _record_key("INVENTORY", inventory.id)
        )

        expected_available = max(
            0,
            inventory.current_stock - inventory.reserved_stock,
        )

        if inventory.reserved_stock < 0 or inventory.current_stock < 0:
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="INVENTORY_NEGATIVE_QUANTITY",
                severity="ERROR",
                module="INVENTORY",
                record_type="INVENTORY",
                record_id=inventory.id,
                record_label=str(inventory.product_id),
                description="Inventory contains a negative stock or reserved quantity.",
                details={
                    "current_stock": inventory.current_stock,
                    "reserved_stock": inventory.reserved_stock,
                },
            )
            issues_detected += 1

            issue_record_keys.add(
                _record_key("INVENTORY", inventory.id)
            )

        if inventory.available_stock != expected_available:
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="INVENTORY_AVAILABLE_STOCK_MISMATCH",
                severity="ERROR",
                module="INVENTORY",
                record_type="INVENTORY",
                record_id=inventory.id,
                record_label=str(inventory.product_id),
                description="Available stock does not match current stock minus reserved stock.",
                details={
                    "current_stock": inventory.current_stock,
                    "reserved_stock": inventory.reserved_stock,
                    "stored_available_stock": inventory.available_stock,
                    "expected_available_stock": expected_available,
                },
            )
            issues_detected += 1

            issue_record_keys.add(
                _record_key("INVENTORY", inventory.id)
            )

        latest_movement = (
            db.query(InventoryMovement)
            .filter(InventoryMovement.inventory_id == inventory.id)
            .order_by(
                InventoryMovement.created_at.desc(),
                InventoryMovement.id.desc(),
            )
            .first()
        )

        if latest_movement is not None:
            if latest_movement.updated_quantity != inventory.current_stock:
                _upsert_issue(
                    db=db,
                    company_id=company_id,
                    issue_type="INVENTORY_MOVEMENT_STOCK_MISMATCH",
                    severity="WARNING",
                    module="INVENTORY",
                    record_type="INVENTORY",
                    record_id=inventory.id,
                    record_label=str(inventory.product_id),
                    description="The latest recorded stock movement does not match current inventory stock.",
                    details={
                        "inventory_current_stock": inventory.current_stock,
                        "latest_movement_id": str(latest_movement.id),
                        "latest_movement_quantity": latest_movement.updated_quantity,
                    },
                )
                issues_detected += 1

                issue_record_keys.add(
                    _record_key("INVENTORY", inventory.id)
                )

    return {
        "records_checked": records_checked,
        "issues_detected": issues_detected,
        "checked_record_keys": checked_record_keys,
        "issue_record_keys": issue_record_keys,
    }

def check_stock_movements(db, company_id):
    """Validate stock movement arithmetic for one company."""
    records_checked = 0
    issues_detected = 0
    checked_record_keys = set()
    issue_record_keys = set()

    movements = (
        db.query(InventoryMovement)
        .join(
            Inventory,
            InventoryMovement.inventory_id == Inventory.id,
        )
        .filter(Inventory.company_id == company_id)
        .all()
    )

    for movement in movements:
        records_checked += 1

        checked_record_keys.add(
            _record_key("INVENTORY_MOVEMENT", movement.id)
        )

        expected_updated = (
            movement.previous_quantity + movement.quantity_changed
        )

        if movement.updated_quantity != expected_updated:
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="STOCK_MOVEMENT_ARITHMETIC_MISMATCH",
                severity="ERROR",
                module="STOCK_MOVEMENTS",
                record_type="INVENTORY_MOVEMENT",
                record_id=movement.id,
                record_label=str(movement.inventory_id),
                description="Stock movement arithmetic is inconsistent.",
                details={
                    "previous_quantity": movement.previous_quantity,
                    "quantity_changed": movement.quantity_changed,
                    "stored_updated_quantity": movement.updated_quantity,
                    "expected_updated_quantity": expected_updated,
                },
            )

            issues_detected += 1

            issue_record_keys.add(
                _record_key("INVENTORY_MOVEMENT", movement.id)
            )

    return {
        "records_checked": records_checked,
        "issues_detected": issues_detected,
        "checked_record_keys": checked_record_keys,
        "issue_record_keys": issue_record_keys,
    }

def check_sales(db, company_id):
    """Validate sales records and reconcile sale totals with their line items."""
    records_checked = 0
    issues_detected = 0
    checked_record_keys = set()
    issue_record_keys = set()

    sales = (
        db.query(Sale)
        .filter(Sale.company_id == company_id)
        .all()
    )

    for sale in sales:
        records_checked += 1

        checked_record_keys.add(
            _record_key("SALE", sale.id)
        )

        missing_fields = []

        if not _normalise_text(sale.invoice_number):
            missing_fields.append("invoice_number")

        if not _normalise_text(sale.customer_name):
            missing_fields.append("customer_name")

        if sale.sale_date is None:
            missing_fields.append("sale_date")

        if sale.sales_channel is None:
            missing_fields.append("sales_channel")

        if sale.payment_method is None:
            missing_fields.append("payment_method")

        if sale.payment_status is None:
            missing_fields.append("payment_status")

        if missing_fields:
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="SALE_REQUIRED_FIELD_MISSING",
                severity="ERROR",
                module="SALES",
                record_type="SALE",
                record_id=sale.id,
                record_label=sale.invoice_number or str(sale.id),
                description="Sale is missing one or more required values.",
                details={"missing_fields": missing_fields},
            )
            issues_detected += 1
            issue_record_keys.add(_record_key("SALE", sale.id))

        if sale.total_amount is None or sale.total_amount < 0:
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="SALE_INVALID_TOTAL",
                severity="ERROR",
                module="SALES",
                record_type="SALE",
                record_id=sale.id,
                record_label=sale.invoice_number or str(sale.id),
                description="Sale total is missing or negative.",
                details={"total_amount": sale.total_amount},
            )
            issues_detected += 1
            issue_record_keys.add(_record_key("SALE", sale.id))

        items = (
            db.query(SaleItem)
            .filter(SaleItem.sale_id == sale.id)
            .all()
        )

        if not items:
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="SALE_WITHOUT_ITEMS",
                severity="ERROR",
                module="SALES",
                record_type="SALE",
                record_id=sale.id,
                record_label=sale.invoice_number or str(sale.id),
                description="Sale has no associated line items.",
                details={},
            )
            issues_detected += 1
            issue_record_keys.add(_record_key("SALE", sale.id))
            continue

        calculated_total = Decimal("0.00")
        invalid_items = []

        for item in items:
            item_problems = []

            if item.quantity is None or item.quantity <= 0:
                item_problems.append("quantity")

            if item.unit_price is None or item.unit_price < 0:
                item_problems.append("unit_price")

            if item.discount is None or item.discount < 0:
                item_problems.append("discount")

            if item.tax is None or item.tax < 0:
                item_problems.append("tax")

            if item.total is None or item.total < 0:
                item_problems.append("total")

            if (
                item.unit_price is not None
                and item.quantity is not None
                and item.discount is not None
                and item.tax is not None
                and item.quantity > 0
                and item.unit_price >= 0
                and item.discount >= 0
                and item.tax >= 0
            ):
                expected_item_total = (
                    item.unit_price * item.quantity
                    - item.discount
                    + item.tax
                )

                if item.total is not None and abs(
                    item.total - expected_item_total
                ) > Decimal("0.01"):
                    item_problems.append("total_calculation")

            if item_problems:
                invalid_items.append({
                    "item_id": str(item.id),
                    "problems": item_problems,
                })

            if item.total is not None:
                calculated_total += item.total

        if invalid_items:
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="SALE_INVALID_LINE_ITEM",
                severity="ERROR",
                module="SALES",
                record_type="SALE",
                record_id=sale.id,
                record_label=sale.invoice_number or str(sale.id),
                description="One or more sale line items contain invalid values.",
                details={"invalid_items": invalid_items},
            )
            issues_detected += 1
            issue_record_keys.add(_record_key("SALE", sale.id))

        if (
            sale.total_amount is not None
            and abs(sale.total_amount - calculated_total) > Decimal("0.01")
        ):
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="SALE_TOTAL_MISMATCH",
                severity="ERROR",
                module="SALES",
                record_type="SALE",
                record_id=sale.id,
                record_label=sale.invoice_number or str(sale.id),
                description="Sale total does not match the sum of its line-item totals.",
                details={
                    "sale_total": sale.total_amount,
                    "calculated_total": calculated_total,
                    "line_item_count": len(items),
                },
            )
            issues_detected += 1
            issue_record_keys.add(_record_key("SALE", sale.id))

    return {
        "records_checked": records_checked,
        "issues_detected": issues_detected,
        "checked_record_keys": checked_record_keys,
        "issue_record_keys": issue_record_keys,
    }

def check_sales_references(db, company_id):
    """Detect sales that reference customers, products, or categories
    belonging to a different company.
    """
    records_checked = 0
    issues_detected = 0
    checked_record_keys = set()
    issue_record_keys = set()

    sales = (
        db.query(Sale)
        .filter(Sale.company_id == company_id)
        .all()
    )

    for sale in sales:
        records_checked += 1

        checked_record_keys.add(
            _record_key("SALE", sale.id)
        )

        if sale.customer_id is not None:
            customer = (
                db.query(Customer)
                .filter(Customer.id == sale.customer_id)
                .first()
            )

            if customer is None or customer.company_id != company_id:
                _upsert_issue(
                    db=db,
                    company_id=company_id,
                    issue_type="SALE_CUSTOMER_REFERENCE_INVALID",
                    severity="ERROR",
                    module="SALES",
                    record_type="SALE",
                    record_id=sale.id,
                    record_label=sale.invoice_number or str(sale.id),
                    description=(
                        "Sale references a customer that is missing "
                        "or belongs to another company."
                    ),
                    details={
                        "customer_id": str(sale.customer_id),
                    },
                )
                issues_detected += 1

                issue_record_keys.add(
                    _record_key("SALE", sale.id)
                )

        items = (
            db.query(SaleItem)
            .filter(SaleItem.sale_id == sale.id)
            .all()
        )

        for item in items:
            product = (
                db.query(Product)
                .filter(Product.id == item.product_id)
                .first()
            )

            category = (
                db.query(Category)
                .filter(Category.id == item.category_id)
                .first()
            )

            if (
                product is not None
                and product.company_id == company_id
                and product.status == ProductStatus.INACTIVE
            ):
                _upsert_issue(
                    db=db,
                    company_id=company_id,
                    issue_type="SALE_PRODUCT_INACTIVE",
                    severity="WARNING",
                    module="SALES",
                    record_type="SALE",
                    record_id=sale.id,
                    record_label=sale.invoice_number or str(sale.id),
                    description="Sale contains a line item referencing an inactive product.",
                    details={
                        "sale_item_id": str(item.id),
                        "product_id": str(item.product_id),
                        "product_status": product.status.value,
                    },
                )
                issues_detected += 1

                issue_record_keys.add(
                    _record_key("SALE", sale.id)
                )

            invalid_references = []

            if product is None or product.company_id != company_id:
                invalid_references.append("product_id")

            if category is None or category.company_id != company_id:
                invalid_references.append("category_id")

            if invalid_references:
                _upsert_issue(
                    db=db,
                    company_id=company_id,
                    issue_type="SALE_ITEM_REFERENCE_INVALID",
                    severity="ERROR",
                    module="SALES",
                    record_type="SALE",
                    record_id=sale.id,
                    record_label=sale.invoice_number or str(sale.id),
                    description=(
                        "A sale line item references a missing product "
                        "or a product/category belonging to another company."
                    ),
                    details={
                        "sale_item_id": str(item.id),
                        "product_id": str(item.product_id),
                        "category_id": str(item.category_id),
                        "invalid_references": invalid_references,
                    },
                )
                issues_detected += 1

                issue_record_keys.add(
                    _record_key("SALE", sale.id)
                )

    return {
        "records_checked": records_checked,
        "issues_detected": issues_detected,
        "checked_record_keys": checked_record_keys,
        "issue_record_keys": issue_record_keys,
    }

def check_sale_stock_movements(db, company_id):
    """Detect sale stock deductions that exceeded stock at transaction time."""
    records_checked = 0
    issues_detected = 0
    checked_record_keys = set()
    issue_record_keys = set()

    sales = (
        db.query(Sale)
        .filter(Sale.company_id == company_id)
        .all()
    )

    for sale in sales:
        records_checked += 1
        record_key = _record_key("SALE", sale.id)
        checked_record_keys.add(record_key)

        movements = (
            db.query(InventoryMovement, Inventory.product_id)
            .join(
                Inventory,
                Inventory.id == InventoryMovement.inventory_id,
            )
            .filter(
                Inventory.company_id == company_id,
                InventoryMovement.quantity_changed < 0,
                InventoryMovement.reason.like(
                    f"Deducted % units for Sale "
                    f"(Invoice: {sale.invoice_number})"
                ),
            )
            .all()
        )

        violations = []

        for movement, product_id in movements:
            quantity_sold = abs(movement.quantity_changed)
            stock_before = movement.previous_quantity

            if stock_before < quantity_sold:
                violations.append({
                    "movement_id": str(movement.id),
                    "product_id": str(product_id),
                    "stock_before_sale": stock_before,
                    "quantity_sold": quantity_sold,
                    "stock_after_movement": movement.updated_quantity,
                    "shortfall": quantity_sold - stock_before,
                    "movement_detected_at": (
                        movement.created_at.isoformat()
                        if movement.created_at else None
                    ),
                })

        if violations:
            _upsert_issue(
                db=db,
                company_id=company_id,
                issue_type="SALE_QUANTITY_EXCEEDS_AVAILABLE_STOCK",
                severity="ERROR",
                module="SALES",
                record_type="SALE",
                record_id=sale.id,
                record_label=sale.invoice_number,
                description=(
                    "A sale attempted to deduct more stock than "
                    "was available before the transaction."
                ),
                details={
                    "invoice_number": sale.invoice_number,
                    "stock_violations": violations,
                },
            )

            issues_detected += 1
            issue_record_keys.add(record_key)

    return {
        "records_checked": records_checked,
        "issues_detected": issues_detected,
        "checked_record_keys": checked_record_keys,
        "issue_record_keys": issue_record_keys,
    }

def run_data_quality_checks(db, company_id, run_started_at=None):
    """Run all data-quality checks and calculate unique record totals."""

    checks = [
        ("products", check_products),
        ("customers", check_customers),
        ("customer_purchase_summaries", check_customer_purchase_summaries),
        ("inventory", check_inventory),
        ("stock_movements", check_stock_movements),
        ("sales", check_sales),
        ("sales_references", check_sales_references),
        ("sale_stock_movements", check_sale_stock_movements),
    ]

    summary = {
        "records_checked": 0,
        "validation_checks_performed": 0,
        "issues_detected": 0,
        "unresolved_issues": 0,
        "valid_records": 0,
        "records_with_issues": 0,
        "checks": {},
    }

    all_checked_record_keys = set()
    all_issue_record_keys = set()

    for check_name, check_function in checks:
        result = check_function(db, company_id)

        all_checked_record_keys.update(
            result["checked_record_keys"]
        )

        all_issue_record_keys.update(
            result["issue_record_keys"]
        )

        summary["validation_checks_performed"] += 1

        summary["issues_detected"] += (
            result["issues_detected"]
        )

        # Store only JSON-safe values in the check summary.
        summary["checks"][check_name] = {
            "records_checked": result["records_checked"],
            "issues_detected": result["issues_detected"],
        }

    db.flush()

    # Count unique records across all validation checks.
    summary["records_checked"] = len(all_checked_record_keys)

    # Count unique records with at least one detected issue.
    summary["records_with_issues"] = len(
        all_issue_record_keys
    )

    # A valid record has been checked and has no detected issues.
    summary["valid_records"] = len(
        all_checked_record_keys - all_issue_record_keys
    )

    summary["unresolved_issues"] = (
        db.query(DataQualityIssue)
        .filter(
            DataQualityIssue.company_id == company_id,
            DataQualityIssue.status.in_(["OPEN", "INVESTIGATING"]),
        )
        .count()
    )

    return summary

def _create_reconciliation_run(db, company_id, user_id=None):
    """Create and persist a reconciliation run before checks begin."""
    run = ReconciliationRun(
        company_id=company_id,
        triggered_by=user_id,
        status="RUNNING",
        started_at=datetime.utcnow(),
        records_checked=0,
        issues_detected=0,
        issues_resolved=0,
        failed_checks=0,
        summary_json=json.dumps({}, default=str),
    )

    db.add(run)
    db.flush()

    return run

def _complete_reconciliation_run(db, run, summary):
    """Mark a reconciliation run as completed and save its summary."""
    run.status = (
    "COMPLETED_WITH_ISSUES"
    if summary.get("issues_detected", 0) > 0
    else "COMPLETED"
    ) 
    run.completed_at = datetime.utcnow()
    run.records_checked = summary.get("records_checked", 0)
    run.issues_detected = summary.get("issues_detected", 0)
    run.issues_resolved = summary.get("issues_resolved", 0)
    run.failed_checks = summary.get("failed_checks", 0)
    run.summary_json = json.dumps(summary, default=str)

    db.flush()

    return run

def _fail_reconciliation_run(db, run, error):
    """Mark a reconciliation run as failed and store the error."""
    run.status = "FAILED"
    run.completed_at = datetime.utcnow()
    run.failed_checks = max(run.failed_checks or 0, 1)
    run.error_message = str(error)[:2000]

    db.flush()

    return run

def execute_reconciliation(db, company_id, user_id=None):
    """
    Execute a reconciliation run and persist its final status.

    A separate commit preserves the run record if the checks fail.
    """
    run = None

    try:
        # Create and persist the run before executing checks.
        run = _create_reconciliation_run(
            db=db,
            company_id=company_id,
            user_id=user_id,
        )
        db.commit()

        # Run the existing data-quality checks.
        summary = run_data_quality_checks(
          db=db,
          company_id=company_id,
          run_started_at=run.started_at,
          )

        # Save the final summary and completion status.
        _complete_reconciliation_run(
            db=db,
            run=run,
            summary=summary,
        )
        db.commit()

        return {
            "run_id": str(run.id),
            "status": run.status,
            "summary": summary,
        }

    except Exception as error:
        # Undo incomplete check changes before saving failure status.
        db.rollback()

        if run is not None:
            try:
                # Reload the persisted run after the rollback.
                run = (
                    db.query(ReconciliationRun)
                    .filter(
                        ReconciliationRun.id == run.id,
                        ReconciliationRun.company_id == company_id,
                    )
                    .one_or_none()
                )

                if run is not None:
                    _fail_reconciliation_run(
                        db=db,
                        run=run,
                        error=error,
                    )
                    db.commit()
            except Exception:
                db.rollback()

        raise

def run_targeted_data_quality_checks(db, company_id, check_names):
    """
    Run selected data-quality checks after a business operation.
    Does not commit. The caller controls the transaction.
    """
    available_checks = {
        "products": check_products,
        "customers": check_customers,
        "customer_purchase_summaries": check_customer_purchase_summaries,
        "inventory": check_inventory,
        "stock_movements": check_stock_movements,
        "sales": check_sales,
        "sales_references": check_sales_references,
        "sale_stock_movements": check_sale_stock_movements,
    }

    results = {}

    for check_name in check_names:
        check_function = available_checks.get(check_name)

        if check_function is None:
            raise ValueError(
                f"Unknown data-quality check: {check_name}"
            )

        results[check_name] = check_function(db, company_id)

    db.flush()
    return results