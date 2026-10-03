"""Shared pytest fixtures.

Runs the whole suite against an isolated, freshly seeded & trained Smart
Cafeteria instance in a temp directory -- never the real demo database or
the real trained model files in backend/models_store/. The environment
variables below must be set before the first `app.*` import happens
anywhere in the process, which is why this module sets them at import time,
at the very top, before pulling in anything from `app`.
"""
import os
import shutil
import tempfile
from datetime import date

import pytest

_TMP_DIR = tempfile.mkdtemp(prefix="smart_cafeteria_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP_DIR, 'test.db')}"
os.environ["MODEL_DIR"] = os.path.join(_TMP_DIR, "models")
os.environ["DEMO_MODE"] = "true"
os.environ.setdefault("JWT_SECRET", "pytest-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app import seed  # noqa: E402
from app.engines import forecasting, trial_conversion, waste  # noqa: E402
from app.main import app  # noqa: E402

TODAY = date.today()


def pytest_sessionstart(session):
    seed.seed_all(verbose=False)
    forecasting.train()
    waste.train()
    trial_conversion.train()


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def login(client):
    def _login(email: str, password: str) -> dict:
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, f"login failed for {email}: {r.text}"
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _login


@pytest.fixture(scope="session")
def admin_headers(login):
    return login("admin@smartcafeteria.io", "admin123")


@pytest.fixture(scope="session")
def kitchen_headers(login):
    """Kitchen manager for institution 1 (corporate)."""
    return login("kitchen.corporate@smartcafeteria.io", "kitchen123")


@pytest.fixture(scope="session")
def kitchen_college_headers(login):
    """Kitchen manager for a different institution (college)."""
    return login("kitchen.college@smartcafeteria.io", "kitchen123")


@pytest.fixture(scope="session")
def coordinator_headers(login):
    return login("coord.corporate@smartcafeteria.io", "coord123")


@pytest.fixture(scope="session")
def ngo_headers(login):
    return login("ngo1@smartcafeteria.io", "ngo123")


@pytest.fixture()
def db_session():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
