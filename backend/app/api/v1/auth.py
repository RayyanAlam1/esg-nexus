from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from app.api.deps import DB, User
from app.core import audit
from app.core.errors import UnauthorizedError
from app.core.security import CAPABILITIES, create_token, decode_token, verify_password
from app.models.identity import Tenant, UserRole
from app.models.identity import User as UserModel
from app.models.organization import Entity

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    #: Tenant slug. Required only when the same address exists in more than one tenant.
    tenant: str | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or " " in v or len(v) > 255:
            raise ValueError("invalid email address")
        return v

    password: str


class RefreshIn(BaseModel):
    refresh_token: str


def _user_payload(db, user: UserModel) -> dict:
    assignments = db.execute(select(UserRole).where(UserRole.user_id == user.id)).scalars().all()
    roles = sorted({r.role_name for r in assignments})
    caps = sorted(c for c, allowed in CAPABILITIES.items() if "*" in allowed or allowed & set(roles))
    entity_ids = sorted({a.entity_id for a in assignments if a.entity_id})
    entity_codes = [e.code for e in db.execute(select(Entity).where(Entity.id.in_(entity_ids)).order_by(Entity.code)).scalars().all()] if entity_ids else []
    tenant = db.get(Tenant, user.tenant_id)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "tenant_id": user.tenant_id,
        "tenant_slug": tenant.slug if tenant else None,
        "roles": roles,
        "capabilities": caps,
        "title": user.title,
        # Empty means unrestricted; otherwise the user may only see these entities.
        "entity_ids": entity_ids,
        "entity_codes": entity_codes,
    }


@router.post("/login")
def login(body: LoginIn, db: DB):
    stmt = select(UserModel).where(UserModel.email == body.email.lower())
    if body.tenant:
        stmt = stmt.join(Tenant, Tenant.id == UserModel.tenant_id).where(Tenant.slug == body.tenant.strip().lower())
    candidates = db.execute(stmt).scalars().all()
    if len(candidates) > 1:
        # The same address may exist in several tenants; never guess which one.
        raise UnauthorizedError("This address exists in more than one tenant. Supply 'tenant' to sign in.")
    user = candidates[0] if candidates else None
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise UnauthorizedError("Invalid credentials")
    payload = _user_payload(db, user)
    audit.record(db, tenant_id=user.tenant_id, user_id=user.id, action="auth.login", object_type="user", object_id=user.id)
    db.commit()
    return {
        "access_token": create_token(user.id, user.tenant_id, payload["roles"]),
        "refresh_token": create_token(user.id, user.tenant_id, payload["roles"], kind="refresh"),
        "token_type": "bearer",
        "user": payload,
    }


@router.post("/refresh")
def refresh(body: RefreshIn, db: DB):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise UnauthorizedError("Refresh token required")
    user = db.get(UserModel, int(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("User inactive")
    up = _user_payload(db, user)
    return {"access_token": create_token(user.id, user.tenant_id, up["roles"]), "token_type": "bearer", "user": up}


@router.get("/me")
def me(principal: User, db: DB):
    user = db.get(UserModel, principal.user_id)
    return _user_payload(db, user)
