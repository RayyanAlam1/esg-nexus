"""Agents, agent runs, model runs, knowledge base (RAG) and evaluations."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, PKMixin, TenantMixin, TimestampMixin, utcnow


class Agent(Base, PKMixin, TimestampMixin):
    __tablename__ = "agents"
    code: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    responsibilities: Mapped[list | None] = mapped_column(JSON)
    tools: Mapped[list | None] = mapped_column(JSON)
    expert_profile: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(16), default="1.0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AgentRun(Base, PKMixin, TenantMixin):
    __tablename__ = "agent_runs"
    agent_code: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    task: Mapped[str] = mapped_column(String(120), nullable=False)
    input: Mapped[dict | None] = mapped_column(JSON)
    output: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="completed")  # completed|failed|blocked|requires_review
    confidence: Mapped[float | None] = mapped_column(Float)
    sources: Mapped[list | None] = mapped_column(JSON)
    tools_used: Mapped[list | None] = mapped_column(JSON)
    guardrail_result: Mapped[dict | None] = mapped_column(JSON)
    evaluation_id: Mapped[int | None] = mapped_column(ForeignKey("evaluations.id"))
    expert: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)

    model_runs: Mapped[list[ModelRun]] = relationship(back_populates="agent_run", cascade="all, delete-orphan")


class ModelRun(Base, PKMixin, TenantMixin):
    __tablename__ = "model_runs"
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(80))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    agent_run: Mapped[AgentRun | None] = relationship(back_populates="model_runs")


class KnowledgeDocument(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_knowledge_docs_tenant_code"),)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # framework|policy|report|methodology|metric_definition|evidence|internal|regulation
    version: Mapped[str] = mapped_column(String(24), default="1")
    source_ref: Mapped[str | None] = mapped_column(String(300))
    freshness_date: Mapped[date | None] = mapped_column(Date)
    permissions: Mapped[dict | None] = mapped_column(JSON)  # {"roles": [...]} — permission-aware RAG
    status: Mapped[str] = mapped_column(String(16), default="approved")  # approved|draft|retired
    meta: Mapped[dict | None] = mapped_column(JSON)

    chunks: Mapped[list[KnowledgeChunk]] = relationship(back_populates="document", cascade="all, delete-orphan", order_by="KnowledgeChunk.chunk_index")


class KnowledgeChunk(Base, PKMixin):
    __tablename__ = "knowledge_chunks"
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON)  # page, section, metric codes
    embedding: Mapped[list | None] = mapped_column(JSON)  # populated when an embedding provider is configured

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class Evaluation(Base, PKMixin, TenantMixin):
    __tablename__ = "evaluations"
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)  # agent_run|report_section|report|dataset|metric
    object_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evaluator: Mapped[str] = mapped_column(String(32), default="evaluation_agent")
    dimension: Mapped[str] = mapped_column(String(24), default="ai")  # ai|data|esg|report
    scores: Mapped[dict] = mapped_column(JSON, nullable=False)
    overall: Mapped[float] = mapped_column(Float, nullable=False)
    findings: Mapped[list | None] = mapped_column(JSON)
    passed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QualityScore(Base, PKMixin, TenantMixin):
    __tablename__ = "quality_scores"
    __table_args__ = (UniqueConstraint("metric_id", "entity_id", "period_id", name="uq_quality_scores_metric_entity_period"),)
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric_definitions.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("reporting_periods.id"), nullable=False)
    completeness: Mapped[float] = mapped_column(Float, default=0)
    accuracy: Mapped[float] = mapped_column(Float, default=0)
    consistency: Mapped[float] = mapped_column(Float, default=0)
    timeliness: Mapped[float] = mapped_column(Float, default=0)
    validity: Mapped[float] = mapped_column(Float, default=0)
    uniqueness: Mapped[float] = mapped_column(Float, default=0)
    traceability: Mapped[float] = mapped_column(Float, default=0)
    overall: Mapped[float] = mapped_column(Float, default=0)
    explanation: Mapped[list | None] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
