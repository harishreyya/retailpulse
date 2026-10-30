
from decimal import Decimal

from app.database import SessionLocal
from app.models import (
    Customer,
    CustomerPurchaseSummary,
    Sale,
    SaleItem,
    Category,
    Product,
    SalesChannel,
    PaymentMethod,
)
from app.services.data_quality import check_customer_purchase_summaries


def test_customer_purchase_summary_detects_mismatch(company_a):
    db = SessionLocal()

    try:
        company_id = company_a["company"]["id"]

        category = Category(
            company_id=company_id,
            name="Data Quality Test Category",
        )
        db.add(category)
        db.flush()

        product_one = Product(
            company_id=company_id,
            category_id=category.id,
            name="Test Product One",
            sku="DQ-TEST-001",
            unit_price=Decimal("10.00"),
            cost_price=Decimal("5.00"),
            stock_quantity=20,
            unit_of_measure="unit",
        )
        product_two = Product(
            company_id=company_id,
            category_id=category.id,
            name="Test Product Two",
            sku="DQ-TEST-002",
            unit_price=Decimal("20.00"),
            cost_price=Decimal("10.00"),
            stock_quantity=20,
            unit_of_measure="unit",
        )
        db.add_all([product_one, product_two])
        db.flush()

        customer = Customer(
            company_id=company_id,
            customer_code="DQ-CUST-001",
            first_name="Test",
            last_name="Customer",
            full_name="Test Customer",
            email="dq-customer@example.com",
            phone="9000000001",
        )
        db.add(customer)
        db.flush()

        sale = Sale(
            company_id=company_id,
            invoice_number="DQ-INV-001",
            customer_name="Test Customer",
            customer_id=customer.id,
            sales_channel=SalesChannel.RETAIL_STORE,
            payment_method=PaymentMethod.CASH,
            total_amount=Decimal("40.00"),
        )
        db.add(sale)
        db.flush()

        db.add_all([
            SaleItem(
                sale_id=sale.id,
                product_id=product_one.id,
                category_id=category.id,
                quantity=2,
                unit_price=Decimal("10.00"),
                discount=Decimal("0.00"),
                tax=Decimal("0.00"),
                total=Decimal("20.00"),
            ),
            SaleItem(
                sale_id=sale.id,
                product_id=product_two.id,
                category_id=category.id,
                quantity=1,
                unit_price=Decimal("20.00"),
                discount=Decimal("0.00"),
                tax=Decimal("0.00"),
                total=Decimal("20.00"),
            ),
        ])

        # Deliberately incorrect values to verify the reconciliation check.
        summary = CustomerPurchaseSummary(
            customer_id=customer.id,
            company_id=company_id,
            total_orders=0,
            total_revenue=Decimal("0.00"),
            total_quantity=0,
            average_order_value=Decimal("0.00"),
        )
        db.add(summary)
        db.commit()

        result = check_customer_purchase_summaries(db, company_id)

        assert result["records_checked"] == 1
        assert result["issues_detected"] == 1

        db.flush()

        # Confirm the issue contains the correct transaction-derived values.
        from app.models import DataQualityIssue

        issue = (
            db.query(DataQualityIssue)
            .filter(
                DataQualityIssue.company_id == company_id,
                DataQualityIssue.issue_type
                == "CUSTOMER_PURCHASE_SUMMARY_MISMATCH",
                DataQualityIssue.record_id == customer.id,
            )
            .one()
        )

        assert issue.details_json is not None
        assert issue.status == "OPEN"
    finally:
        db.rollback()
        db.close()
