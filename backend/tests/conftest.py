"""Test fixtures: an isolated SQLite database seeded once per session with the ECORP reference dataset,
the offline (deterministic) AI provider, and authenticated clients per role."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="esg_nexus_test_"))
os.environ["ESG_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["ESG_AI_PROVIDER"] = "offline"
os.environ["ESG_ENVIRONMENT"] = "test"
os.environ["ESG_LOCAL_STORAGE_DIR"] = str(_TMP / "storage")
os.environ["ESG_SECRET_KEY"] = "test-secret-key-for-esg-nexus-tests-0123456789"
os.environ["ESG_RATE_LIMIT_PER_MINUTE"] = "100000"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

CREDENTIALS = {
    "admin": ("admin@esgnexus.local", "Admin!2024"),
    "executive": ("cso@ecorp.local", "Exec!2024"),
    "manager": ("manager@ecorp.local", "Manager!2024"),
    "analyst": ("analyst@ecorp.local", "Analyst!2024"),
    "contributor": ("contributor@ecorp.local", "Data!2024"),
    "reviewer": ("reviewer@ecorp.local", "Review!2024"),
    "approver": ("approver@ecorp.local", "Approve!2024"),
    "auditor": ("auditor@ecorp.local", "Audit!2024"),
}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # lifespan → create tables + seed (~10 s once)
        yield c


@pytest.fixture(scope="session")
def tokens(client):
    out = {}
    for role, (email, pw) in CREDENTIALS.items():
        r = client.post("/api/v1/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 200, r.text
        out[role] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return out


@pytest.fixture(scope="session")
def db_session(client):
    from app.core.db import SessionLocal

    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture(scope="session")
def ctx(db_session):
    """Common ORM handles: tenant, org, group entity, FY2023/FY2022 periods."""
    from sqlalchemy import select

    from app.models import Entity, Organization, ReportingPeriod, Tenant

    db = db_session
    tenant = db.execute(select(Tenant)).scalars().first()
    org = db.execute(select(Organization)).scalars().first()
    return {
        "db": db,
        "tenant": tenant,
        "org": org,
        "group": db.execute(select(Entity).where(Entity.code == "ECORP")).scalars().first(),
        "efert": db.execute(select(Entity).where(Entity.code == "EFERT")).scalars().first(),
        "fy2023": db.execute(select(ReportingPeriod).where(ReportingPeriod.code == "FY2023")).scalars().first(),
        "fy2022": db.execute(select(ReportingPeriod).where(ReportingPeriod.code == "FY2022")).scalars().first(),
    }


def metric(db, code):
    from sqlalchemy import select

    from app.models import MetricDefinition

    return db.execute(select(MetricDefinition).where(MetricDefinition.code == code)).scalars().first()
