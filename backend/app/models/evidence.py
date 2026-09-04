from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, PKMixin, TenantMixin, TimestampMixin

EVIDENCE_KINDS = [
    "report_page",
    "invoice",
    "utility_bill",
    "hr_report",
    "safety_report",
    "environmental_record",
    "audit_document",
    "certification",
    "policy",
    "contract",
    "supplier_document",
    "measurement_record",
    "spreadsheet",
    "pdf",
    "image",
    "assurance_statement",
    "financial_statement",
    "regulatory_filing",
    "other",
]


class Evidence(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "evidence"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_evidence_tenant_code"),)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str | None] = mapped_column(String(255))  # originating system / organisation
    document_ref: Mapped[str | None] = mapped_column(String(255))  # file name / URL / document id
    page_from: Mapped[int | None] = mapped_column(Integer)
    page_to: Mapped[int | None] = mapped_column(Integer)
    printed_page: Mapped[str | None] = mapped_column(String(24))
    excerpt: Mapped[str | None] = mapped_column(Text)
    evidence_date: Mapped[date | None] = mapped_column(Date)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id"))
    period_id: Mapped[int | None] = mapped_column(ForeignKey("reporting_periods.id"))
    verification_status: Mapped[str] = mapped_column(String(16), default="unverified")  # unverified|verified|rejected
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    confidence: Mapped[float | None] = mapped_column(Float)
    version: Mapped[int] = mapped_column(Integer, default=1)
    file_hash: Mapped[str | None] = mapped_column(String(80))
    storage_key: Mapped[str | None] = mapped_column(String(300))
    permissions: Mapped[dict | None] = mapped_column(JSON)
    meta: Mapped[dict | None] = mapped_column(JSON)

    links: Mapped[list[EvidenceLink]] = relationship(back_populates="evidence", cascade="all, delete-orphan")


class EvidenceLink(Base, PKMixin, TimestampMixin):
    """Metric → Evidence → Source. A link can target a metric definition, a specific value, a requirement or a report section."""

    __tablename__ = "evidence_links"
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id", ondelete="CASCADE"), index=True, nullable=False)
    metric_id: Mapped[int | None] = mapped_column(ForeignKey("metric_definitions.id", ondelete="CASCADE"), index=True)
    metric_value_id: Mapped[int | None] = mapped_column(ForeignKey("metric_values.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[int | None] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    report_section_id: Mapped[int | None] = mapped_column(ForeignKey("report_sections.id", ondelete="CASCADE"))
    relation: Mapped[str] = mapped_column(String(16), default="supports")  # supports|contradicts|context
    note: Mapped[str | None] = mapped_column(Text)

    evidence: Mapped[Evidence] = relationship(back_populates="links")
