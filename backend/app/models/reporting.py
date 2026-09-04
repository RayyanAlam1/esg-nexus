from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, PKMixin, TenantMixin, TimestampMixin, utcnow

REPORT_STATES = ["draft", "ai_generated", "validating", "requires_review", "reviewed", "approved", "published", "blocked"]


class ReportTemplate(Base, PKMixin, TimestampMixin):
    __tablename__ = "report_templates"
    code: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sections: Mapped[list] = mapped_column(JSON, nullable=False)  # ordered section config
    tenant_id: Mapped[int | None] = mapped_column(Integer)


class Report(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "reports"
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("reporting_periods.id"), nullable=False)
    template_code: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    framework_codes: Mapped[list] = mapped_column(JSON, default=list)
    scope: Mapped[dict | None] = mapped_column(JSON)  # {entity_codes: [...]}
    status: Mapped[str] = mapped_column(String(24), default="draft")
    readiness: Mapped[dict | None] = mapped_column(JSON)
    validation_result: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked: Mapped[bool] = mapped_column(Boolean, default=False)

    sections: Mapped[list[ReportSection]] = relationship(back_populates="report", cascade="all, delete-orphan", order_by="ReportSection.sort_order")
    versions: Mapped[list[ReportVersion]] = relationship(back_populates="report", cascade="all, delete-orphan")


class ReportSection(Base, PKMixin, TimestampMixin):
    __tablename__ = "report_sections"
    __table_args__ = (UniqueConstraint("report_id", "code", name="uq_report_sections_report_code"),)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    content_md: Mapped[str | None] = mapped_column(Text)
    narrative_source: Mapped[str] = mapped_column(String(16), default="template")  # ai|human|template|data
    status: Mapped[str] = mapped_column(String(24), default="draft")
    metric_codes: Mapped[list | None] = mapped_column(JSON)
    evidence_codes: Mapped[list | None] = mapped_column(JSON)
    requirement_codes: Mapped[list | None] = mapped_column(JSON)
    tables: Mapped[list | None] = mapped_column(JSON)  # rendered data tables
    charts: Mapped[list | None] = mapped_column(JSON)
    evaluation_id: Mapped[int | None] = mapped_column(ForeignKey("evaluations.id"))
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    comments: Mapped[list | None] = mapped_column(JSON)

    report: Mapped[Report] = relationship(back_populates="sections")


class ReportVersion(Base, PKMixin, TenantMixin):
    __tablename__ = "report_versions"
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)  # pdf|docx|xlsx|csv|html
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(80))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)

    report: Mapped[Report] = relationship(back_populates="versions")
