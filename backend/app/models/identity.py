from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, PKMixin, TimestampMixin


class Tenant(Base, PKMixin, TimestampMixin):
    __tablename__ = "tenants"
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    deployment_model: Mapped[str] = mapped_column(String(32), default="saas")  # saas|private_cloud|on_prem|air_gapped
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base, PKMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    title: Mapped[str | None] = mapped_column(String(120))

    roles: Mapped[list[UserRole]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Role(Base, PKMixin):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(400))


class UserRole(Base, PKMixin):
    """Role assignment optionally scoped to an organization and/or entity (business-unit access)."""

    __tablename__ = "user_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id"), nullable=True)

    user: Mapped[User] = relationship(back_populates="roles")
