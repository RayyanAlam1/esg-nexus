from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, PKMixin, TenantMixin, TimestampMixin


class MaterialityAssessment(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "materiality_assessments"
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("reporting_periods.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    methodology: Mapped[str | None] = mapped_column(Text)
    approach: Mapped[str] = mapped_column(String(16), default="double")  # impact|financial|double
    threshold: Mapped[float] = mapped_column(Float, default=3.0)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    evidence_codes: Mapped[list | None] = mapped_column(JSON)

    topics: Mapped[list[MaterialityTopic]] = relationship(back_populates="assessment", cascade="all, delete-orphan")
    stakeholder_inputs: Mapped[list[StakeholderInput]] = relationship(back_populates="assessment", cascade="all, delete-orphan")


class MaterialityTopic(Base, PKMixin, TimestampMixin):
    __tablename__ = "materiality_topics"
    assessment_id: Mapped[int] = mapped_column(ForeignKey("materiality_assessments.id", ondelete="CASCADE"), index=True, nullable=False)
    topic_code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    pillar: Mapped[str] = mapped_column(String(24), nullable=False)
    impact_severity: Mapped[float | None] = mapped_column(Float)  # 1-5
    impact_likelihood: Mapped[float | None] = mapped_column(Float)  # 1-5
    impact_score: Mapped[float | None] = mapped_column(Float)
    financial_magnitude: Mapped[float | None] = mapped_column(Float)
    financial_likelihood: Mapped[float | None] = mapped_column(Float)
    financial_score: Mapped[float | None] = mapped_column(Float)
    stakeholder_priority: Mapped[float | None] = mapped_column(Float)
    is_material: Mapped[bool] = mapped_column(Boolean, default=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    related_metric_codes: Mapped[list | None] = mapped_column(JSON)
    related_requirement_codes: Mapped[list | None] = mapped_column(JSON)
    risks: Mapped[list | None] = mapped_column(JSON)
    opportunities: Mapped[list | None] = mapped_column(JSON)
    evidence_codes: Mapped[list | None] = mapped_column(JSON)

    assessment: Mapped[MaterialityAssessment] = relationship(back_populates="topics")


class StakeholderInput(Base, PKMixin, TimestampMixin):
    __tablename__ = "stakeholder_inputs"
    assessment_id: Mapped[int] = mapped_column(ForeignKey("materiality_assessments.id", ondelete="CASCADE"), index=True, nullable=False)
    stakeholder_group: Mapped[str] = mapped_column(String(120), nullable=False)
    topic_code: Mapped[str | None] = mapped_column(String(48))
    priority: Mapped[float | None] = mapped_column(Float)
    channel: Mapped[str | None] = mapped_column(String(200))
    concern: Mapped[str | None] = mapped_column(Text)
    engagement_value: Mapped[str | None] = mapped_column(Text)

    assessment: Mapped[MaterialityAssessment] = relationship(back_populates="stakeholder_inputs")
