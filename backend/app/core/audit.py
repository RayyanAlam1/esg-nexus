"""Immutable-style audit trail writer (append-only; no update/delete API is exposed)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def record(
    db: Session,
    *,
    tenant_id: int,
    user_id: int | None,
    action: str,
    object_type: str,
    object_id: str | int | None = None,
    old_value: Any = None,
    new_value: Any = None,
    reason: str | None = None,
    ip: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        ip=ip,
    )
    db.add(entry)
    db.flush()
    return entry
