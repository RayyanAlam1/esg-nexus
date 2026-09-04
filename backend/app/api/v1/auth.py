from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from app.api.deps import DB, User
from app.core import audit
from app.core.errors import UnauthorizedError
from app.core.security import CAPABILITIES, create_token, decode_token, verify_password
from app.models.identity import User as UserModel
from app.models.identity import UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str

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
    roles = sorted({r.role_name for r in db.execute(select(UserRole).where(UserRole.user_id == user.id)).scalars().all()})
    caps = sorted(c for c, allowed in CAPABILITIES.items() if "*" in allowed or allowed & set(roles))
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "tenant_id": user.tenant_id, "roles": roles, "capabilities": caps, "title": user.title}


@router.post("/login")
def login(body: LoginIn, db: DB):
    user = db.execute(select(UserModel).where(UserModel.email == body.email.lower())).scalars().first()
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
