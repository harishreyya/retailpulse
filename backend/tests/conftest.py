"""
Shared fixtures for the Task 13 (Audit Logs) test suite.

Requires a real Postgres database to run against — the models use
Postgres-specific UUID/Enum column types throughout, so SQLite can't
stand in here. Point TEST_DATABASE_URL at a disposable test database
before running:

    export TEST_DATABASE_URL=postgresql://postgres:password@localhost:5432/retailpulse_test
    pytest backend/tests -v

Each test gets a clean set of tables (dropped and recreated) so tests
don't leak state into each other via a shared company_id collision etc.
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-this-is-at-least-32-characters-long")
os.environ.setdefault("DATABASE_URL", os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/retailpulse_test"
))

from app.database import Base  # noqa: E402
import app.database as app_database  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(os.environ["DATABASE_URL"])
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean_db(engine):
    """Full schema reset before every test. Simplest way to guarantee
    test isolation given how many tables/relationships this app has."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client(engine, monkeypatch):
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(app_database, "SessionLocal", TestSessionLocal)

    # main.py runs its own startup migrations/ALTER statements against
    # `engine`/`SessionLocal` at import time; importing here (after the
    # schema has already been created fresh by clean_db) exercises that
    # exact startup path the same way `uvicorn main:app` would.
    import importlib
    import main as main_module
    importlib.reload(main_module)

    with TestClient(main_module.app) as c:
        yield c


def _register_company(client, suffix: str) -> dict:
    payload = {
        "company_name": f"Test Co {suffix}",
        "company_email": f"company{suffix}@example.com",
        "owner_name": f"Admin {suffix}",
        "owner_email": f"admin{suffix}@example.com",
        "password": "TestPassword123!",
        "confirm_password": "TestPassword123!",
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def company_a(client):
    """Registers Company A and returns {company, user, tokens, headers}."""
    data = _register_company(client, uuid.uuid4().hex[:8])
    headers = {"Authorization": f"Bearer {data['tokens']['access_token']}"}
    return {**data, "headers": headers, "client": client}


@pytest.fixture
def company_b(client):
    """A second, unrelated company — used for cross-tenant isolation tests."""
    data = _register_company(client, uuid.uuid4().hex[:8])
    headers = {"Authorization": f"Bearer {data['tokens']['access_token']}"}
    return {**data, "headers": headers, "client": client}


def create_product(client, headers, name="Test Widget", sku=None, price=100, stock=50):
    sku = sku or f"SKU-{uuid.uuid4().hex[:8].upper()}"
    cat = client.post("/categories", json={"name": f"Cat-{uuid.uuid4().hex[:6]}"}, headers=headers)
    assert cat.status_code in (200, 201), cat.text
    payload = {
        "name": name, "sku": sku, "category_id": cat.json()["id"],
        "unit_price": price, "cost_price": price * 0.6, "stock_quantity": stock,
        "unit_of_measure": "unit",
    }
    resp = client.post("/products", json=payload, headers=headers)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()
