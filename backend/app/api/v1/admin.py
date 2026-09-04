from __future__ import annotations

import platform
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select, text

from app.api.deps import DB, User, serialize
from app.core import audit
from app.core.config import get_settings
from app.core.db import engine
from app.core.errors import NotFoundError
from app.core.security import ROLES, hash_password, require
from app.models.ai import AgentRun, ModelRun
from app.models.audit import AuditLog, Notification
from app.models.esg import MetricDefinition, MetricValue
from app.models.evidence import Evidence
from app.models.governance import Issue
from app.models.identity import Tenant, UserRole
from app.models.identity import User as UserModel
from app.models.organization import Entity, Organization

router = APIRouter(prefix="/admin", tags=["administration"])
STARTED = time.time()


class UserIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or " " in v or len(v) > 255:
            raise ValueError("invalid email address")
        return v

    full_name: str
    password: str
    roles: list[str]
    entity_code: str | None = None
    title: str | None = None


class RolesIn(BaseModel):
    roles: list[str]


@router.get("/users", dependencies=[Depends(require("admin"))])
def users(principal: User, db: DB):
    rows = db.execute(select(UserModel).where(UserModel.tenant_id == principal.tenant_id).order_by(UserModel.email)).scalars().all()
    return [
        {
            **serialize(u, exclude={"password_hash"}),
            "roles": sorted({r.role_name for r in u.roles}),
            "entity_scope": [db.get(Entity, r.entity_id).code for r in u.roles if r.entity_id],
        }
        for u in rows
    ]


@router.post("/users", dependencies=[Depends(require("admin"))])
def create_user(body: UserIn, principal: User, db: DB):
    if any(r not in ROLES for r in body.roles):
        from app.core.errors import AppError

        raise AppError(f"Unknown role; valid roles: {ROLES}")
    org = db.execute(select(Organization).where(Organization.tenant_id == principal.tenant_id)).scalars().first()
    u = UserModel(tenant_id=principal.tenant_id, email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password), title=body.title)
    db.add(u)
    db.flush()
    entity = db.execute(select(Entity).where(Entity.tenant_id == principal.tenant_id, Entity.code == body.entity_code)).scalars().first() if body.entity_code else None
    for r in body.roles:
        db.add(UserRole(user_id=u.id, role_name=r, organization_id=org.id if org else None, entity_id=entity.id if entity else None))
    audit.record(
        db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="user.create", object_type="user", object_id=u.id, new_value={"email": u.email, "roles": body.roles}
    )
    db.commit()
    return {**serialize(u, exclude={"password_hash"}), "roles": body.roles}


@router.put("/users/{user_id}/roles", dependencies=[Depends(require("admin"))])
def set_roles(user_id: int, body: RolesIn, principal: User, db: DB):
    u = db.get(UserModel, user_id)
    if u is None or u.tenant_id != principal.tenant_id:
        raise NotFoundError("User not found")
    old = sorted({r.role_name for r in u.roles})
    org = db.execute(select(Organization).where(Organization.tenant_id == principal.tenant_id)).scalars().first()
    for r in list(u.roles):
        db.delete(r)
    for r in body.roles:
        db.add(UserRole(user_id=u.id, role_name=r, organization_id=org.id if org else None))
    audit.record(db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="user.roles", object_type="user", object_id=u.id, old_value=old, new_value=body.roles)
    db.commit()
    return {"user_id": u.id, "roles": body.roles}


@router.get("/roles")
def roles(principal: User, db: DB):
    from app.core.security import CAPABILITIES

    return [{"name": r, "capabilities": sorted(c for c, allowed in CAPABILITIES.items() if "*" in allowed or r in allowed)} for r in ROLES]


@router.get("/system", dependencies=[Depends(require("admin"))])
def system(principal: User, db: DB):
    s = get_settings()
    counts = {
        "metric_definitions": db.execute(select(func.count(MetricDefinition.id)).where(MetricDefinition.tenant_id == principal.tenant_id)).scalar(),
        "metric_values": db.execute(select(func.count(MetricValue.id)).where(MetricValue.tenant_id == principal.tenant_id)).scalar(),
        "evidence": db.execute(select(func.count(Evidence.id)).where(Evidence.tenant_id == principal.tenant_id)).scalar(),
        "open_issues": db.execute(select(func.count(Issue.id)).where(Issue.tenant_id == principal.tenant_id, Issue.status.in_(["open", "acknowledged"]))).scalar(),
        "agent_runs": db.execute(select(func.count(AgentRun.id)).where(AgentRun.tenant_id == principal.tenant_id)).scalar(),
        "model_runs": db.execute(select(func.count(ModelRun.id)).where(ModelRun.tenant_id == principal.tenant_id)).scalar(),
        "audit_entries": db.execute(select(func.count(AuditLog.id)).where(AuditLog.tenant_id == principal.tenant_id)).scalar(),
    }
    tenant = db.get(Tenant, principal.tenant_id)
    return {
        "app": s.app_name,
        "environment": s.environment,
        "database": engine.url.get_backend_name(),
        "ai_provider": s.ai_provider,
        "model": s.anthropic_model,
        "embedding_provider": s.embedding_provider,
        "tenant": serialize(tenant),
        "uptime_seconds": int(time.time() - STARTED),
        "python": platform.python_version(),
        "counts": counts,
        "config": {
            "ai_confidence_threshold": s.ai_confidence_threshold,
            "rate_limit_per_minute": s.rate_limit_per_minute,
            "auto_seed": s.auto_seed,
            "frameworks_dir": str(s.frameworks_dir),
            "seed_dir": str(s.seed_dir),
        },
    }


@router.post("/reseed", dependencies=[Depends(require("tenant.admin"))])
def reseed(principal: User, db: DB, recompute: bool = True):
    from app.seed import Seeder

    stats = Seeder(db).run(recompute=recompute)
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="admin.reseed",
        object_type="tenant",
        object_id=principal.tenant_id,
        new_value={k: v for k, v in stats.items() if not isinstance(v, list)},
    )
    db.commit()
    return stats


@router.get("/notifications")
def notifications(principal: User, db: DB, unread: bool = False):
    stmt = select(Notification).where(Notification.tenant_id == principal.tenant_id, (Notification.user_id == principal.user_id) | (Notification.user_id.is_(None)))
    if unread:
        stmt = stmt.where(Notification.is_read == False)  # noqa: E712
    return serialize(db.execute(stmt.order_by(Notification.created_at.desc()).limit(50)).scalars().all())


health_router = APIRouter(tags=["health"])


@health_router.get("/health")
def health():
    return {"status": "ok", "app": get_settings().app_name, "uptime_seconds": int(time.time() - STARTED)}


@health_router.get("/health/ready")
def ready(db: DB):
    from fastapi.responses import JSONResponse

    try:
        db.execute(text("SELECT 1"))
        tenants = db.execute(select(func.count(Tenant.id))).scalar()
        return {"status": "ready", "database": "ok", "tenants": tenants, "seeded": tenants > 0}
    except Exception as exc:  # pragma: no cover
        return JSONResponse(status_code=503, content={"status": "degraded", "error": str(exc)})
