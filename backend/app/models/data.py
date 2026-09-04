"""Data sources, datasets, versions and records (ingestion pipeline persistence)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, PKMixin, TenantMixin, TimestampMixin, utcnow


class DataSource(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_data_sources_tenant_code"),)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # csv|excel|json|api|database|erp|hr|ems|environmental|document|pdf|scanned|manual
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(120))
    system_name: Mapped[str | None] = mapped_column(String(120))  # e.g. SAP, SuccessFactors, VelocityEHS
    config: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    datasets: Mapped[list[Dataset]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Dataset(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "datasets"
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    period_id: Mapped[int | None] = mapped_column(ForeignKey("reporting_periods.id"))
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id"))
    pillar: Mapped[str | None] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), default="active")
    permissions: Mapped[dict | None] = mapped_column(JSON)  # {"roles": [...]} dataset-level access

    source: Mapped[DataSource] = relationship(back_populates="datasets")
    versions: Mapped[list[DatasetVersion]] = relationship(back_populates="dataset", cascade="all, delete-orphan", order_by="DatasetVersion.version")


class DatasetVersion(Base, PKMixin, TenantMixin):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_dataset_versions_dataset_version"),)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_hash: Mapped[str | None] = mapped_column(String(80))
    storage_key: Mapped[str | None] = mapped_column(String(300))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="received")  # received|validated|normalized|loaded|failed
    validation_result: Mapped[dict | None] = mapped_column(JSON)
    transformation_history: Mapped[list | None] = mapped_column(JSON)
    quality: Mapped[dict | None] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), index=True)

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    records: Mapped[list[DatasetRecord]] = relationship(back_populates="version", cascade="all, delete-orphan")


class DatasetRecord(Base, PKMixin):
    __tablename__ = "dataset_records"
    version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True, nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    metric_code: Mapped[str | None] = mapped_column(String(80), index=True)
    entity_code: Mapped[str | None] = mapped_column(String(40))
    period_code: Mapped[str | None] = mapped_column(String(24))
    value: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(40))
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    issues: Mapped[list | None] = mapped_column(JSON)
    mapping_confidence: Mapped[float | None] = mapped_column(Float)

    version: Mapped[DatasetVersion] = relationship(back_populates="records")
