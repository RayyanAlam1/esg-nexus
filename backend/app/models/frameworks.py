"""Configuration-driven framework registry."""

from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, PKMixin, TenantMixin, TimestampMixin


class Framework(Base, PKMixin, TimestampMixin):
    __tablename__ = "frameworks"
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    jurisdiction: Mapped[str | None] = mapped_column(String(80))
    industry: Mapped[str | None] = mapped_column(String(120))
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # null = global

    versions: Mapped[list[FrameworkVersion]] = relationship(back_populates="framework", cascade="all, delete-orphan")


class FrameworkVersion(Base, PKMixin, TimestampMixin):
    __tablename__ = "framework_versions"
    __table_args__ = (UniqueConstraint("framework_id", "version", name="uq_framework_versions_fw_version"),)
    framework_id: Mapped[int] = mapped_column(ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="current")  # current|superseded|draft
    source_url: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)

    framework: Mapped[Framework] = relationship(back_populates="versions")
    requirements: Mapped[list[Requirement]] = relationship(back_populates="framework_version", cascade="all, delete-orphan", order_by="Requirement.sort_order")


class Requirement(Base, PKMixin, TimestampMixin):
    __tablename__ = "requirements"
    __table_args__ = (UniqueConstraint("framework_version_id", "code", name="uq_requirements_fwv_code"),)
    framework_version_id: Mapped[int] = mapped_column(ForeignKey("framework_versions.id", ondelete="CASCADE"), index=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("requirements.id"))
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    pillar: Mapped[str | None] = mapped_column(String(24))
    theme: Mapped[str | None] = mapped_column(String(120))
    disclosure_type: Mapped[str] = mapped_column(String(16), default="both")  # quantitative|narrative|both
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_core: Mapped[bool] = mapped_column(Boolean, default=True)
    applicability: Mapped[dict | None] = mapped_column(JSON)  # {industries: [], jurisdictions: [], conditions: []}
    metric_codes: Mapped[list | None] = mapped_column(JSON)  # default metric mappings from configuration
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    guidance: Mapped[str | None] = mapped_column(Text)

    framework_version: Mapped[FrameworkVersion] = relationship(back_populates="requirements")


class FrameworkMapping(Base, PKMixin, TenantMixin, TimestampMixin):
    """Tenant-specific mapping of a requirement to a metric (or narrative)."""

    __tablename__ = "framework_mappings"
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"), index=True, nullable=False)
    metric_id: Mapped[int | None] = mapped_column(ForeignKey("metric_definitions.id", ondelete="CASCADE"), index=True)
    mapping_type: Mapped[str] = mapped_column(String(16), default="direct")  # direct|partial|derived|narrative|omitted
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="approved")  # proposed|approved|rejected
    confidence: Mapped[float | None] = mapped_column(Float)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    omission_reason: Mapped[str | None] = mapped_column(Text)


class OrganizationFramework(Base, PKMixin, TenantMixin, TimestampMixin):
    """Frameworks selected for an organisation + period during project setup."""

    __tablename__ = "organization_frameworks"
    __table_args__ = (UniqueConstraint("organization_id", "framework_version_id", "period_id", name="uq_org_frameworks"),)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    framework_version_id: Mapped[int] = mapped_column(ForeignKey("framework_versions.id"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("reporting_periods.id"), nullable=False)
    applicable_scope: Mapped[dict | None] = mapped_column(JSON)  # {entities: [], industry, jurisdiction}
    status: Mapped[str] = mapped_column(String(16), default="active")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
