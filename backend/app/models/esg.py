"""ESG taxonomy, metric definitions, values, targets and calculations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, PKMixin, TenantMixin, TimestampMixin, utcnow

if TYPE_CHECKING:
    from app.models.evidence import EvidenceLink


class EsgTopic(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "esg_topics"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_topics_tenant_code"),)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    pillar: Mapped[str] = mapped_column(String(24), nullable=False)  # environment|social|governance|prosperity
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    subtopics: Mapped[list[EsgSubtopic]] = relationship(back_populates="topic", cascade="all, delete-orphan")


class EsgSubtopic(Base, PKMixin, TimestampMixin):
    __tablename__ = "esg_subtopics"
    __table_args__ = (UniqueConstraint("topic_id", "code", name="uq_subtopics_topic_code"),)
    topic_id: Mapped[int] = mapped_column(ForeignKey("esg_topics.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    topic: Mapped[EsgTopic] = relationship(back_populates="subtopics")


class MetricDefinition(Base, PKMixin, TenantMixin, TimestampMixin):
    """Metadata definition for every metric."""

    __tablename__ = "metric_definitions"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_metric_definitions_tenant_code"),)
    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    pillar: Mapped[str] = mapped_column(String(24), nullable=False)
    topic_code: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    subtopic_code: Mapped[str | None] = mapped_column(String(48))
    unit: Mapped[str | None] = mapped_column(String(40))
    frequency: Mapped[str] = mapped_column(String(16), default="annual")
    data_type: Mapped[str] = mapped_column(String(16), default="decimal")  # decimal|integer|percentage|ratio|boolean|text|currency|count
    kind: Mapped[str] = mapped_column(String(16), default="raw")  # raw|derived|ratio|intensity|percentage|yoy|aggregate|narrative|target
    calculation_method: Mapped[str | None] = mapped_column(Text)
    formula: Mapped[str | None] = mapped_column(Text)  # {CODE} expression evaluated by the metric engine
    required_inputs: Mapped[list | None] = mapped_column(JSON)
    data_sources: Mapped[list | None] = mapped_column(JSON)
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=True)
    evidence_requirements: Mapped[str | None] = mapped_column(Text)
    applicable_frameworks: Mapped[list | None] = mapped_column(JSON)  # requirement codes e.g. WEF.PLANET.GHG
    materiality_topic: Mapped[str | None] = mapped_column(String(48))
    assurance_status: Mapped[str] = mapped_column(String(16), default="not_assured")  # not_assured|limited|reasonable
    validation_rules: Mapped[dict | None] = mapped_column(JSON)  # {min, max, allowed, max_yoy_change_pct}
    aggregation: Mapped[str] = mapped_column(String(16), default="sum")  # sum|weighted_avg|avg|last|none|max
    direction: Mapped[str | None] = mapped_column(String(16))  # lower_is_better|higher_is_better|neutral
    tags: Mapped[list | None] = mapped_column(JSON)
    is_kpi: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    owner: Mapped[str | None] = mapped_column(String(120))

    values: Mapped[list[MetricValue]] = relationship(back_populates="metric", cascade="all, delete-orphan")


class MetricValue(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "metric_values"
    __table_args__ = (UniqueConstraint("metric_id", "entity_id", "period_id", name="uq_metric_values_metric_entity_period"),)
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric_definitions.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True, nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("reporting_periods.id"), index=True, nullable=False)
    value_numeric: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|validated|approved|final
    source_type: Mapped[str] = mapped_column(String(16), default="manual")  # manual|ingested|calculated|extracted|reported
    dataset_version_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_versions.id"), nullable=True)
    calculation_run_id: Mapped[int | None] = mapped_column(ForeignKey("calculation_runs.id"), nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    metric: Mapped[MetricDefinition] = relationship(back_populates="values")
    evidence_links: Mapped[list[EvidenceLink]] = relationship(primaryjoin="MetricValue.id==foreign(EvidenceLink.metric_value_id)", viewonly=True)


class Target(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "targets"
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric_definitions.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    baseline_period_id: Mapped[int | None] = mapped_column(ForeignKey("reporting_periods.id"))
    target_period_id: Mapped[int | None] = mapped_column(ForeignKey("reporting_periods.id"))
    target_year: Mapped[int | None] = mapped_column(Integer)
    baseline_value: Mapped[float | None] = mapped_column(Float)
    target_value: Mapped[float | None] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(12), default="decrease")  # decrease|increase|maintain|achieve
    kind: Mapped[str] = mapped_column(String(16), default="absolute")  # absolute|relative_pct|intensity|qualitative
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|achieved|missed|not_set
    source_evidence_code: Mapped[str | None] = mapped_column(String(64))


class CalculationVersion(Base, PKMixin, TenantMixin, TimestampMixin):
    """Versioned, approved formula for a derived metric."""

    __tablename__ = "calculation_versions"
    __table_args__ = (UniqueConstraint("metric_id", "version", name="uq_calc_versions_metric_version"),)
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric_definitions.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    methodology_ref: Mapped[str | None] = mapped_column(String(200))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class CalculationRun(Base, PKMixin, TenantMixin):
    """Deterministic execution record — the lineage anchor for every calculated value."""

    __tablename__ = "calculation_runs"
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric_definitions.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("reporting_periods.id"), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(16), nullable=False)
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False)  # {code: {value, metric_value_id, entity, period}}
    result: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok|missing_inputs|error
    message: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    executed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
