from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, PKMixin, TenantMixin, utcnow


class AuditLog(Base, PKMixin, TenantMixin):
    __tablename__ = "audit_logs"
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    object_id: Mapped[str | None] = mapped_column(String(64), index=True)
    old_value: Mapped[dict | list | str | None] = mapped_column(JSON)
    new_value: Mapped[dict | list | str | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Notification(Base, PKMixin, TenantMixin):
    __tablename__ = "notifications"
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
