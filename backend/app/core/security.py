"""Authentication, password hashing, JWT and RBAC dependencies.

Roles: super_admin, org_admin, esg_manager, esg_analyst, data_contributor, reviewer, auditor,
executive, report_approver. Permissions are role → capability mappings kept in one place so a new
capability is an additive change.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import PermissionError_, UnauthorizedError

ROLES = [
    "super_admin",
    "org_admin",
    "esg_manager",
    "esg_analyst",
    "data_contributor",
    "reviewer",
    "auditor",
    "executive",
    "report_approver",
]

# capability → roles allowed. "*" = every authenticated user.
CAPABILITIES: dict[str, set[str]] = {
    "read": {"*"},
    "data.write": {"super_admin", "org_admin", "esg_manager", "esg_analyst", "data_contributor"},
    "data.delete": {"super_admin", "org_admin", "esg_manager"},
    "metric.write": {"super_admin", "org_admin", "esg_manager", "esg_analyst"},
    "metric.validate": {"super_admin", "org_admin", "esg_manager", "esg_analyst"},
    "metric.approve": {"super_admin", "org_admin", "esg_manager"},
    "evidence.write": {"super_admin", "org_admin", "esg_manager", "esg_analyst", "data_contributor"},
    "evidence.verify": {"super_admin", "org_admin", "esg_manager", "reviewer", "auditor"},
    "framework.manage": {"super_admin", "org_admin", "esg_manager"},
    "governance.manage": {"super_admin", "org_admin"},
    "governance.exception": {"super_admin", "org_admin", "esg_manager"},
    "ai.run": {"super_admin", "org_admin", "esg_manager", "esg_analyst", "reviewer", "executive"},
    "review": {"super_admin", "org_admin", "esg_manager", "reviewer"},
    "report.build": {"super_admin", "org_admin", "esg_manager", "esg_analyst"},
    "report.approve": {"super_admin", "org_admin", "report_approver"},
    "report.publish": {"super_admin", "org_admin", "report_approver"},
    "audit.read": {"super_admin", "org_admin", "auditor", "esg_manager", "executive", "reviewer", "report_approver"},
    "admin": {"super_admin", "org_admin"},
    "tenant.admin": {"super_admin"},
}

# Workflow transitions: who may move an object into a state.
WORKFLOW_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"super_admin", "org_admin", "esg_manager", "esg_analyst", "data_contributor"},
    "ai_generated": {"super_admin", "org_admin", "esg_manager", "esg_analyst"},
    "validating": {"super_admin", "org_admin", "esg_manager", "esg_analyst"},
    "requires_review": {"super_admin", "org_admin", "esg_manager", "esg_analyst"},
    "reviewed": {"super_admin", "org_admin", "esg_manager", "reviewer"},
    "approved": {"super_admin", "org_admin", "report_approver"},
    "published": {"super_admin", "org_admin", "report_approver"},
    "rejected": {"super_admin", "org_admin", "esg_manager", "reviewer", "report_approver"},
}


# --- password hashing (PBKDF2-SHA256, no compiled dependency) ---------------------------------
def hash_password(password: str, *, iterations: int = 310_000) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except Exception:  # pragma: no cover
        return False


# --- JWT -------------------------------------------------------------------------------------
def create_token(subject: int, tenant_id: int, roles: list[str], *, kind: str = "access") -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    exp = now + (timedelta(minutes=settings.access_token_minutes) if kind == "access" else timedelta(days=settings.refresh_token_days))
    payload = {"sub": str(subject), "tid": tenant_id, "roles": roles, "type": kind, "iat": now, "exp": exp}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid token") from exc


# --- Principal ----------------------------------------------------------------------------------
@dataclass
class Principal:
    user_id: int
    tenant_id: int
    email: str
    roles: list[str] = field(default_factory=list)
    organization_ids: list[int] = field(default_factory=list)  # empty = all orgs in tenant
    entity_ids: list[int] = field(default_factory=list)  # empty = all entities

    def has(self, capability: str) -> bool:
        allowed = CAPABILITIES.get(capability, set())
        return "*" in allowed or bool(allowed & set(self.roles))

    def can_transition(self, state: str) -> bool:
        return bool(WORKFLOW_TRANSITIONS.get(state, set()) & set(self.roles))


bearer = HTTPBearer(auto_error=False)


def get_principal(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> Principal:
    from app.models.identity import User, UserRole  # local import to avoid cycles

    if creds is None:
        raise UnauthorizedError("Missing bearer token")
    payload = decode_token(creds.credentials)
    if payload.get("type") != "access":
        raise UnauthorizedError("Access token required")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    assignments = db.query(UserRole).filter(UserRole.user_id == user.id).all()
    principal = Principal(
        user_id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        roles=sorted({a.role_name for a in assignments}),
        organization_ids=sorted({a.organization_id for a in assignments if a.organization_id}),
        entity_ids=sorted({a.entity_id for a in assignments if a.entity_id}),
    )
    request.state.principal = principal
    return principal


def require(capability: str):
    def _dep(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if not principal.has(capability):
            raise PermissionError_(f"Capability '{capability}' required", details={"roles": principal.roles})
        return principal

    return _dep


CurrentUser = Annotated[Principal, Depends(get_principal)]
