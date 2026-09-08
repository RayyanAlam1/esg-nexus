"""Regression tests for the m0 stabilisation fixes: cross-tenant isolation, tenant-ambiguous login,
evidence path traversal, the production configuration guard, entity-scoped defaults, entity scope
survival across role changes, and string-only report validation details."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import DEFAULT_SECRET_KEY, Settings, get_settings
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.esg import MetricDefinition
from app.models.evidence import Evidence
from app.models.governance import Issue
from app.models.identity import Tenant, User, UserRole
from app.models.organization import Entity, Organization, ReportingPeriod

#: Exists in the seeded ECORP tenant and is one of the executive-overview KPI cards.
SHARED_METRIC_CODE = "ENV.GHG.SCOPE1_2_TOTAL"
#: Seeded ECORP address, deliberately duplicated into the second tenant.
SHARED_EMAIL = "manager@ecorp.local"
ECORP_PASSWORD = "Manager!2024"
RIVAL_SLUG = "rival-holdings"
RIVAL_PASSWORD = "Rival!2024"


@pytest.fixture(scope="module")
def rival(db_session):
    """A second tenant created through the ORM and removed again, so the shared seed is untouched."""
    db = db_session
    tenant = Tenant(slug=RIVAL_SLUG, name="Rival Holdings", deployment_model="saas")
    db.add(tenant)
    db.flush()
    org = Organization(tenant_id=tenant.id, code="RIVAL", name="Rival Holdings Limited")
    db.add(org)
    db.flush()
    entity = Entity(tenant_id=tenant.id, organization_id=org.id, code="RIVAL_GRP", name="Rival Group", kind="group")
    period = ReportingPeriod(tenant_id=tenant.id, organization_id=org.id, code="FY2023", label="FY2023", start_date=date(2023, 1, 1), end_date=date(2023, 12, 31))
    metric = MetricDefinition(tenant_id=tenant.id, code=SHARED_METRIC_CODE, name="Rival Scope 1+2 emissions", pillar="environment", topic_code="ENV.GHG", unit="tCO2e")
    db.add_all([entity, period, metric])
    db.flush()
    user = User(tenant_id=tenant.id, email=SHARED_EMAIL, full_name="Rival ESG Manager", password_hash=hash_password(RIVAL_PASSWORD), is_active=True)
    db.add(user)
    db.flush()
    role = UserRole(user_id=user.id, role_name="esg_manager", organization_id=org.id, entity_id=entity.id)
    issue = Issue(
        tenant_id=tenant.id,
        code="RIVAL-SECRET-001",
        severity="CRITICAL",
        category="data_quality",
        title="Rival tenant issue that must never leak",
        metric_code=SHARED_METRIC_CODE,
        entity_code="RIVAL_GRP",
        period_code="FY2023",
        status="open",
    )
    db.add_all([role, issue])
    db.commit()
    handles = {"tenant_id": tenant.id, "user_id": user.id, "entity_id": entity.id, "issue_id": issue.id, "issue_code": issue.code}
    yield handles

    # Nothing relates Tenant to User in the ORM, so the unit of work cannot order these deletes:
    # flush each level explicitly, children first.
    stale_audit = db.execute(select(AuditLog).where((AuditLog.tenant_id == tenant.id) | (AuditLog.user_id == user.id))).scalars().all()
    for level in (stale_audit, [issue, role], [user], [metric, period], [entity], [org], [tenant]):
        for obj in level:
            db.delete(obj)
        db.flush()
    db.commit()


def _open_issue_count(db, metric_code: str, tenant_id: int | None = None) -> int:
    """Open/acknowledged issues on a metric code, optionally scoped to one tenant."""
    from sqlalchemy import func

    stmt = select(func.count(Issue.id)).where(Issue.metric_code == metric_code, Issue.status.in_(["open", "acknowledged"]))
    if tenant_id is not None:
        stmt = stmt.where(Issue.tenant_id == tenant_id)
    return db.execute(stmt).scalar()


def _issue_counts(db, tenant_id: int) -> tuple[int, int]:
    """(own-tenant count, all-tenant count) — the gap is what a missing tenant filter would leak."""
    own = _open_issue_count(db, SHARED_METRIC_CODE, tenant_id)
    every = _open_issue_count(db, SHARED_METRIC_CODE)
    assert every > own, "the rival tenant's issue is missing, so this test would prove nothing"
    return own, every


# --------------------------------------------------------------------------- 1. tenant isolation
def test_metric_detail_never_returns_another_tenants_issues(client, tokens, ctx, rival):
    """A second tenant's issue on the same metric code must not appear in an ECORP metric drilldown."""
    expected, _ = _issue_counts(ctx["db"], ctx["tenant"].id)
    detail = client.get(f"/api/v1/metrics/{SHARED_METRIC_CODE}/detail", headers=tokens["analyst"]).json()
    returned = detail["issues"]
    assert rival["issue_code"] not in [i["code"] for i in returned]
    assert rival["issue_id"] not in [i["id"] for i in returned]
    assert all(i["tenant_id"] == ctx["tenant"].id for i in returned)
    assert len(returned) == expected


def test_kpi_card_issue_count_never_counts_another_tenants_issues(client, tokens, ctx, rival):
    """The overview KPI card's open-issue count is scoped to the caller's tenant."""
    expected, leaked = _issue_counts(ctx["db"], ctx["tenant"].id)
    body = client.get("/api/v1/esg/overview", headers=tokens["executive"]).json()
    card = next(k for k in body["kpis"] if k["code"] == SHARED_METRIC_CODE)
    assert card["open_issues"] == expected != leaked
    assert rival["issue_id"] not in [i["id"] for i in body["issues"]["top"]]


# --------------------------------------------------------------------------- 2. ambiguous login
def test_login_refuses_to_guess_when_the_address_exists_in_two_tenants(client, rival):
    """An address present in more than one tenant is rejected with 401 rather than silently resolved."""
    r = client.post("/api/v1/auth/login", json={"email": SHARED_EMAIL, "password": ECORP_PASSWORD})
    assert r.status_code == 401
    assert "more than one tenant" in r.json()["error"]["message"]


def test_login_with_an_explicit_tenant_slug_signs_into_that_tenant(client, ctx, rival):
    """Supplying the tenant slug disambiguates the login and lands the caller in the right tenant."""
    ecorp = client.post("/api/v1/auth/login", json={"email": SHARED_EMAIL, "password": ECORP_PASSWORD, "tenant": ctx["tenant"].slug})
    assert ecorp.status_code == 200, ecorp.text
    assert ecorp.json()["user"]["tenant_id"] == ctx["tenant"].id

    other = client.post("/api/v1/auth/login", json={"email": SHARED_EMAIL, "password": RIVAL_PASSWORD, "tenant": RIVAL_SLUG})
    assert other.status_code == 200, other.text
    assert other.json()["user"]["tenant_id"] == rival["tenant_id"]
    # The ECORP password must not open the rival tenant, and vice versa.
    assert client.post("/api/v1/auth/login", json={"email": SHARED_EMAIL, "password": ECORP_PASSWORD, "tenant": RIVAL_SLUG}).status_code == 401


# --------------------------------------------------------------------------- 3. evidence traversal
def test_evidence_upload_cannot_escape_the_storage_directory(client, tokens, ctx, db_session):
    """A traversal payload in `code` and `filename` must not place a file outside local_storage_dir."""
    settings = get_settings()
    root = settings.local_storage_dir.resolve()
    hostile_code = "../../../../etc/pwned"
    hostile_name = "../../evil.pdf"
    escape_target = Path(os.path.normpath(str(settings.local_storage_dir / "evidence" / f"{hostile_code}_{hostile_name}")))

    r = client.post(
        "/api/v1/evidence/upload",
        files={"file": (hostile_name, b"traversal probe", "application/pdf")},
        data={"code": hostile_code, "title": "traversal probe", "kind": "pdf"},
        headers=tokens["analyst"],
    )
    assert r.status_code == 200, r.text
    assert not escape_target.exists(), f"file escaped the storage root: {escape_target}"

    ev = r.json()
    stored = Path(ev["storage_key"]).resolve()
    try:
        assert stored.is_relative_to(root)
        assert stored.parent == root / "evidence" / str(ctx["tenant"].id)
        assert stored.is_file()
        assert ".." not in stored.name
        assert "pwned" not in stored.name and "evil" not in stored.name
        assert stored.suffix == ".pdf"
    finally:
        stored.unlink(missing_ok=True)
        row = db_session.get(Evidence, ev["id"])
        if row is not None:
            db_session.delete(row)
            db_session.commit()


# --------------------------------------------------------------------------- 4. production config
def test_production_settings_refuse_a_weak_secret_key(monkeypatch):
    """A deployed environment must not start on the placeholder or a short secret key."""
    monkeypatch.delenv("ESG_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError) as placeholder:
        Settings(environment="production")
    assert "ESG_SECRET_KEY" in str(placeholder.value)

    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key="too-short")
    with pytest.raises(ValidationError):
        Settings(environment="staging", secret_key=DEFAULT_SECRET_KEY)

    strong = "u" * 32
    assert Settings(environment="production", secret_key=strong).secret_key == strong
    assert Settings(environment="development").secret_key == DEFAULT_SECRET_KEY  # dev keeps working


def test_seeding_is_disabled_in_deployed_environments(monkeypatch):
    """The demo dataset is only ever seeded in development and test."""
    monkeypatch.delenv("ESG_SECRET_KEY", raising=False)
    strong = "u" * 32
    assert Settings(environment="production", secret_key=strong).seeding_enabled is False
    assert Settings(environment="staging", secret_key=strong).seeding_enabled is False
    assert Settings(environment="development").seeding_enabled is True
    assert Settings(environment="test").seeding_enabled is True


# --------------------------------------------------------------------------- 5. default entity
def test_scoped_user_without_an_entity_parameter_gets_an_entity_it_may_see(client, tokens):
    """Omitting `entity` resolves to one of a scoped user's own entities instead of a 403 on the group."""
    me = client.get("/api/v1/auth/me", headers=tokens["contributor"]).json()
    assert me["entity_codes"], "the seeded contributor is expected to be entity-scoped"
    r = client.get("/api/v1/esg/overview", headers=tokens["contributor"])
    assert r.status_code == 200, r.text
    assert r.json()["entity"]["code"] in me["entity_codes"]


# --------------------------------------------------------------------------- 6. role replacement
def test_replacing_roles_preserves_the_users_entity_scope(client, tokens, db_session):
    """Rewriting a user's roles must not silently widen them to every entity in the tenant."""
    db = db_session
    user = db.execute(select(User).where(User.email == "contributor@ecorp.local")).scalars().first()
    original = [(r.role_name, r.organization_id, r.entity_id) for r in db.execute(select(UserRole).where(UserRole.user_id == user.id)).scalars().all()]
    scoped_entity_ids = sorted({eid for _, _, eid in original if eid})
    assert scoped_entity_ids, "the seeded contributor is expected to be entity-scoped"

    try:
        r = client.put(f"/api/v1/admin/users/{user.id}/roles", json={"roles": ["data_contributor", "reviewer"]}, headers=tokens["admin"])
        assert r.status_code == 200, r.text
        db.expire_all()
        after = db.execute(select(UserRole).where(UserRole.user_id == user.id)).scalars().all()
        assert sorted({a.role_name for a in after}) == ["data_contributor", "reviewer"]
        assert sorted({a.entity_id for a in after}) == scoped_entity_ids
        assert all(a.entity_id is not None for a in after)
    finally:
        for row in db.execute(select(UserRole).where(UserRole.user_id == user.id)).scalars().all():
            db.delete(row)
        db.flush()
        for role_name, org_id, entity_id in original:
            db.add(UserRole(user_id=user.id, role_name=role_name, organization_id=org_id, entity_id=entity_id))
        db.commit()


def test_replacing_roles_preserves_scope_for_a_multi_entity_user(client, tokens, db_session):
    """A user scoped to several entities keeps every one of them: an empty scope means unrestricted."""
    db = db_session
    user = db.execute(select(User).where(User.email == "contributor@ecorp.local")).scalars().first()
    assert user is not None
    original = [(r.role_name, r.organization_id, r.entity_id) for r in db.execute(select(UserRole).where(UserRole.user_id == user.id)).scalars().all()]
    org_id = original[0][1]
    first_entity = next(eid for _, _, eid in original if eid)
    second_entity = db.execute(select(Entity).where(Entity.id != first_entity, Entity.organization_id == org_id)).scalars().first()
    assert second_entity is not None

    try:
        # Give the user a second scoped entity, then replace their roles.
        db.add(UserRole(user_id=user.id, role_name="data_contributor", organization_id=org_id, entity_id=second_entity.id))
        db.commit()
        expected = sorted({first_entity, second_entity.id})

        r = client.put(f"/api/v1/admin/users/{user.id}/roles", json={"roles": ["data_contributor"]}, headers=tokens["admin"])
        assert r.status_code == 200, r.text
        db.expire_all()
        after = db.execute(select(UserRole).where(UserRole.user_id == user.id)).scalars().all()
        assert sorted({a.entity_id for a in after}) == expected, "a multi-entity user must not be widened to the whole tenant"
        assert all(a.entity_id is not None for a in after)
    finally:
        for row in db.execute(select(UserRole).where(UserRole.user_id == user.id)).scalars().all():
            db.delete(row)
        db.flush()
        for role_name, organization_id, entity_id in original:
            db.add(UserRole(user_id=user.id, role_name=role_name, organization_id=organization_id, entity_id=entity_id))
        db.commit()


def test_uploaded_document_reference_is_reduced_to_a_base_filename(client, tokens):
    """The stored document reference is displayed to users, so it never keeps a caller-supplied path."""
    r = client.post(
        "/api/v1/evidence/upload",
        files={"file": ("../../evil.pdf", b"%PDF-1.4 test", "application/pdf")},
        data={"code": "EV-DOCREF-TEST", "title": "Document reference sanitisation", "kind": "pdf"},
        headers=tokens["manager"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["document_ref"] == "evil.pdf"


# --------------------------------------------------------------------------- 7. validation details
def test_report_validation_details_are_always_strings(client, tokens):
    """Every validation detail and blocking reason is a string, so the preview page can render it."""
    created = client.post("/api/v1/reports", json={"period_code": "FY2023", "template_code": "WEF_CORE", "framework_codes": ["WEF_SCM", "UNGC"]}, headers=tokens["manager"])
    assert created.status_code == 200, created.text
    report_id = created.json()["id"]

    result = client.post(f"/api/v1/reports/{report_id}/validate", headers=tokens["manager"]).json()
    assert result["checks"], result
    for check in result["checks"]:
        assert isinstance(check["detail"], str), f"{check['check']} detail is {type(check['detail']).__name__}: {check['detail']!r}"
        assert check["detail"].strip()
    assert result["reason"], "a freshly created report has unapproved sections and must be blocked"
    for reason in result["reason"]:
        assert isinstance(reason, str), f"reason entry is {type(reason).__name__}: {reason!r}"


# --------------------------------------------------------------------------- 8. global framework reload
def test_framework_reload_is_restricted_to_platform_administrators(client, tokens):
    """The framework registry is shared reference data, so a tenant framework manager cannot reload it."""
    assert client.post("/api/v1/frameworks/reload", headers=tokens["manager"]).status_code == 403
