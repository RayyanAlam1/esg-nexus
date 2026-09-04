from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, PKMixin, TenantMixin, TimestampMixin


class Organization(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_organizations_tenant_code"),)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    legal_form: Mapped[str | None] = mapped_column(String(120))
    headquarters: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(80))
    stock_ticker: Mapped[str | None] = mapped_column(String(40))
    sector: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    reporting_boundary: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(200))
    contact: Mapped[dict | None] = mapped_column(JSON)

    entities: Mapped[list[Entity]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    periods: Mapped[list[ReportingPeriod]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Entity(Base, PKMixin, TenantMixin, TimestampMixin):
    """Node in the organisational hierarchy: group → subsidiary/JV/associate → business unit → facility."""

    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_entities_tenant_code"),)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # group|subsidiary|joint_venture|associate|business_unit|facility|office|plant|foundation|trading
    ownership_pct: Mapped[float | None] = mapped_column(Float)
    consolidation_method: Mapped[str] = mapped_column(String(24), default="full")  # full|proportional|equity|excluded
    in_reporting_boundary: Mapped[bool] = mapped_column(Boolean, default=True)
    country: Mapped[str | None] = mapped_column(String(80))
    region: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict | None] = mapped_column(JSON)  # e.g. water_stressed: true, certifications
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    organization: Mapped[Organization] = relationship(back_populates="entities")
    parent: Mapped[Entity | None] = relationship(remote_side="Entity.id", backref="children")


class ReportingPeriod(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "reporting_periods"
    __table_args__ = (UniqueConstraint("tenant_id", "organization_id", "code", name="uq_periods_org_code"),)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(24), nullable=False)  # FY2023, 2023-Q1, 2023-03
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    granularity: Mapped[str] = mapped_column(String(12), default="year")  # year|quarter|month|custom
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|closed|published
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)

    organization: Mapped[Organization] = relationship(back_populates="periods")
