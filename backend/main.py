from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import Base, engine, SessionLocal
from app.config import settings
from app.routers import auth, categories, products, dashboard, sales, notifications, inventory, analytics, customers, forecasting, inventory_forecast, imports as data_imports, audit_logs, reports, report_schedules, data_quality
from app.models.data_quality import (
    DataQualityIssue,
    ReconciliationRun,
    DataQualityIssueEvent,
)
# Creates tables that don't exist yet (including `sales`, `sale_items`,
# `notifications` from Task 3, and `customers`, `customer_purchase_summary`,
# `customer_activities` from Task 6). It will NOT alter tables that already
# exist — for those, run the guarded ALTER TABLE statements below.
Base.metadata.create_all(bind=engine)

# Task 2: entity_name on the already-existing audit_logs table.
# Task 3: low_stock_threshold / is_out_of_stock on the already-existing
# products table. create_all() can't add columns to a table it didn't
# create, so these run on every startup — safe to run repeatedly.
with engine.connect() as conn:
    conn.execute(text(
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS entity_name VARCHAR(255)"
    ))
    conn.execute(text(
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS details VARCHAR(500)"
    ))
    conn.execute(text(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS low_stock_threshold INTEGER NOT NULL DEFAULT 10"
    ))
    conn.execute(text(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_out_of_stock BOOLEAN NOT NULL DEFAULT FALSE"
    ))
    conn.execute(text(
        # Bug fix: routers/inventory_forecast.py already filtered on
        # Product.supplier (and the serializer already read it), but the
        # column never existed — using the Supplier filter on the
        # Inventory Forecast page crashed with AttributeError.
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier VARCHAR(255)"
    ))
    # Add MANUAL_ADJUSTMENT notification type to enum in DB if not already present
    try:
        conn.execute(text(
            "ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'MANUAL_ADJUSTMENT'"
        ))
    except Exception:
        pass
    conn.commit()

    # Task 6: customer_id links on the already-existing `sales` and
    # `notifications` tables, plus the new customer-related notification
    # types. The `customers` table itself is brand new and was already
    # created by create_all() above, so this FK is safe to add here.
    conn.execute(text(
        "ALTER TABLE sales ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id) ON DELETE SET NULL"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_sales_customer_id ON sales (customer_id)"
    ))
    conn.execute(text(
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id) ON DELETE CASCADE"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_notifications_customer_id ON notifications (customer_id)"
    ))
    for new_value in ["CUSTOMER_REGISTERED", "CUSTOMER_VIP", "CUSTOMER_INACTIVE", "CUSTOMER_FIRST_PURCHASE"]:
        try:
            conn.execute(text(f"ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS '{new_value}'"))
        except Exception:
            pass
    conn.commit()

    # Task 7: forecasting notification types. `demand_forecasts` and
    # `forecast_history` are brand-new tables already created by
    # create_all() above, so no ALTER TABLE is needed for them.
    for new_value in ["FORECAST_STOCK_RUNOUT", "FORECAST_DEMAND_EXCEEDS_STOCK", "FORECAST_DEMAND_GROWTH"]:
        try:
            conn.execute(text(f"ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS '{new_value}'"))
        except Exception:
            pass
    conn.commit()

    # Task 8: structured name fields, postal code, and soft delete on the
    # already-existing `customers` table from Task 6.
    conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS first_name VARCHAR(150) NOT NULL DEFAULT ''"))
    conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS last_name VARCHAR(150) NOT NULL DEFAULT ''"))
    conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS postal_code VARCHAR(30)"))
    conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE"))
    conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP"))
    # Backfill first/last name for rows created before this column existed.
    # COALESCE(...,'') matters here: a single-word full_name (e.g. "viji")
    # has no space, so the substr() below would otherwise evaluate to NULL
    # and violate the NOT NULL constraint on last_name.
    conn.execute(text(
        "UPDATE customers SET "
        "first_name = split_part(full_name, ' ', 1), "
        "last_name = COALESCE(NULLIF(substr(full_name, length(split_part(full_name, ' ', 1)) + 2), ''), '') "
        "WHERE first_name = '' AND full_name IS NOT NULL"
    ))
    # Replace the old always-on unique constraints with partial indexes that
    # only apply to non-deleted customers, so a soft-deleted customer's
    # email/phone can be reused by a new registration.
    conn.execute(text("ALTER TABLE customers DROP CONSTRAINT IF EXISTS uq_customers_company_email"))
    conn.execute(text("ALTER TABLE customers DROP CONSTRAINT IF EXISTS uq_customers_company_phone"))
    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_company_email_live "
        "ON customers (company_id, email) WHERE is_deleted = FALSE"
    ))
    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_company_phone_live "
        "ON customers (company_id, phone) WHERE is_deleted = FALSE"
    ))
    conn.commit()

    # Task 9: payment status and notes on the already-existing `sales` table.
    conn.execute(text(
        "DO $$ BEGIN "
        "CREATE TYPE paymentstatus AS ENUM ('PENDING','PAID','PARTIALLY_PAID','REFUNDED'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$;"
    ))
    conn.execute(text(
        "ALTER TABLE sales ADD COLUMN IF NOT EXISTS payment_status paymentstatus NOT NULL DEFAULT 'PAID'"
    ))
    conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS notes VARCHAR(1000)"))
    conn.commit()

    # Task 10/11 mentor review: DemandForecast.last_accuracy cache column.
    conn.execute(text(
        "ALTER TABLE demand_forecasts ADD COLUMN IF NOT EXISTS last_accuracy NUMERIC(5,4)"
    ))
    conn.commit()

    # Task 12: Data Import notification type.
    try:
        conn.execute(text(
            "ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'DATA_IMPORT_COMPLETED'"
        ))
    except Exception:
        pass
    conn.commit()

    # Task 13: Audit Logs & Activity Monitoring — new columns + status enum
    # on the already-existing `audit_logs` table.
    conn.execute(text(
        "DO $$ BEGIN "
        "CREATE TYPE auditstatus AS ENUM ('SUCCESS','FAILED'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$;"
    ))
    conn.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS resource_type VARCHAR(50)"))
    conn.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS resource_id VARCHAR(64)"))
    conn.execute(text(
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS status auditstatus NOT NULL DEFAULT 'SUCCESS'"
    ))
    conn.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS before_values TEXT"))
    conn.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS after_values TEXT"))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_resource_type ON audit_logs (resource_type)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_resource_id ON audit_logs (resource_id)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_status ON audit_logs (status)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_timestamp ON audit_logs (timestamp)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_company_timestamp ON audit_logs (company_id, timestamp)"
    ))
    conn.commit()

    # Task 14: Notification & Alert Management. `user_id` moves
    # notifications from company-wide broadcast rows to one row per
    # recipient (see services/notifications.py docstring for why). Old
    # rows predate that model and have no natural owner to backfill, so
    # they're dropped here rather than guessed at; correctly-shaped
    # notifications get regenerated going forward via the on-read
    # inventory scan and the various notify_*() call sites.
    conn.execute(text(
        "DO $$ BEGIN "
        "CREATE TYPE notificationpriority AS ENUM ('LOW','MEDIUM','HIGH','CRITICAL'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$;"
    ))
    conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE"))
    conn.execute(text("DELETE FROM notifications WHERE user_id IS NULL"))
    conn.execute(text("ALTER TABLE notifications ALTER COLUMN user_id SET NOT NULL"))
    conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS resource_type VARCHAR(50)"))
    conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS resource_id VARCHAR(64)"))
    conn.execute(text(
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS priority notificationpriority NOT NULL DEFAULT 'LOW'"
    ))
    conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS title VARCHAR(150) NOT NULL DEFAULT 'Notification'"))
    conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(150)"))
    conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS read_at TIMESTAMP"))
    for new_value in ["STOCKOUT_RISK", "OVERSTOCK", "SALES_ALERT", "IMPORT_COMPLETED", "IMPORT_FAILED", "SYSTEM_ALERT"]:
        try:
            conn.execute(text(f"ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS '{new_value}'"))
        except Exception:
            pass
    conn.commit()
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_notifications_user_created ON notifications (user_id, created_at)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_notifications_dedupe ON notifications (user_id, dedupe_key, is_read)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_notifications_priority ON notifications (priority)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_notifications_type ON notifications (type)"
    ))
    conn.commit()
with SessionLocal() as db:
    from app.models import Product, Inventory
    from app.services.inventory_utils import compute_stock_status

    DEFAULT_REORDER_LEVEL = 10
    missing = db.query(Product).outerjoin(
        Inventory, Inventory.product_id == Product.id
    ).filter(Inventory.id.is_(None)).all()

    for product in missing:
        stock = product.stock_quantity or 0
        db.add(Inventory(
            company_id=product.company_id,
            product_id=product.id,
            current_stock=stock,
            reserved_stock=0,
            available_stock=stock,
            reorder_level=DEFAULT_REORDER_LEVEL,
            stock_status=compute_stock_status(stock, DEFAULT_REORDER_LEVEL),
        ))
    if missing:
        db.commit()

app = FastAPI(
    title="RetailPulse Analytics API",
    description="Company onboarding, product/category management, and sales transactions",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(dashboard.router)
app.include_router(sales.router)
app.include_router(notifications.router)
app.include_router(inventory.router)
app.include_router(analytics.router)
app.include_router(customers.router)
app.include_router(forecasting.router)
app.include_router(inventory_forecast.router)
app.include_router(data_imports.router)
app.include_router(audit_logs.router)
app.include_router(reports.router)
app.include_router(report_schedules.router)
app.include_router(data_quality.router)


# ---------------------------------------------------------------------
# Task 15: scheduled report execution.
#
# This project has no Celery/Redis, so a full distributed task queue
# would be disproportionate infrastructure for "check once a minute
# whether any report schedule is due." APScheduler's BackgroundScheduler
# runs an in-process job on its own thread instead — the same philosophy
# as this app's existing "evaluate on read" patterns (inventory alerts,
# inactive-customer scanning), just on a timer instead of a request.
#
# Caveat worth knowing: this only works correctly with a single backend
# process/worker. Running multiple uvicorn workers would mean multiple
# schedulers all picking up the same due schedules independently. If this
# app is ever deployed with >1 worker, this needs either a DB-level lock
# around run_due_schedules, or moving to a real job queue.
# ---------------------------------------------------------------------
from apscheduler.schedulers.background import BackgroundScheduler  # noqa: E402
from app.services.report_schedules import run_due_schedules  # noqa: E402

_scheduler = BackgroundScheduler(timezone="UTC")


def _run_due_schedules_job():
    db = SessionLocal()
    try:
        run_due_schedules(db)
    except Exception:
        db.rollback()
    finally:
        db.close()


@app.on_event("startup")
def _start_scheduler():
    _scheduler.add_job(_run_due_schedules_job, "interval", minutes=1, id="report_schedules", replace_existing=True)
    _scheduler.start()


@app.on_event("shutdown")
def _stop_scheduler():
    _scheduler.shutdown(wait=False)


@app.get("/health")
def health_check():
    return {"status": "ok"}