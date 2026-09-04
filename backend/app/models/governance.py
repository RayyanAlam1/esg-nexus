"""Governance-as-Code, issues (criticality engine) and approvals (human-in-the-loop)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, PKMixin, TenantMixin, TimestampMixin

SEVERITIES = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
RULE_ACTIONS = [
    "BLOCK",
    "WARN",
    "ESCALATE",
    "REQUIRE_APPROVAL",
    "REQUIRE_EVIDENCE",
    "REQUIRE_HUMAN_REVIEW",
    "PREVENT_DATA_MODIFICATION",
    "BLOCK_REPORT_GENERATION",
]


class GovernancePolicy(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "governance_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_policies_tenant_code"),)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64))  # ethics|hse|data|reporting|tax|hr|security
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(16), default="1.0")
    effective_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="active")
    evidence_code: Mapped[str | None] = mapped_column(String(64))
    external_ref: Mapped[str | None] = mapped_column(String(300))


class GovernanceRule(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "governance_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_rules_tenant_code"),)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(12), default="MEDIUM")
    scope: Mapped[str] = mapped_column(String(24), nullable=False)  # metric_value|report|ai_output|data_change|requirement
    condition: Mapped[str] = mapped_column(Text, nullable=False)  # safe expression over the context
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    required_action: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(16), default="1.0")
    effective_date: Mapped[date | None] = mapped_column(Date)
    approval_status: Mapped[str] = mapped_column(String(16), default="approved")  # draft|approved|retired
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    params: Mapped[dict | None] = mapped_column(JSON)
    policy_code: Mapped[str | None] = mapped_column(String(48))


class Issue(Base, PKMixin, TenantMixin, TimestampMixin):
    """Criticality engine output: every issue affects report readiness."""

    __tablename__ = "issues"
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(12), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)  # evidence_gap|data_missing|data_quality|inconsistency|framework_gap|governance|ai_quality|approval|target
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metric_code: Mapped[str | None] = mapped_column(String(80), index=True)
    entity_code: Mapped[str | None] = mapped_column(String(40))
    period_code: Mapped[str | None] = mapped_column(String(24))
    requirement_code: Mapped[str | None] = mapped_column(String(64))
    rule_code: Mapped[str | None] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|acknowledged|resolved|exception_approved
    required_action: Mapped[str | None] = mapped_column(Text)
    blocks_report: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[str | None] = mapped_column(String(120), index=True)


class Approval(Base, PKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "approvals"
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)  # metric_value|report_section|report|ai_output|exception|mapping
    object_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(24), default="requires_review")
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str | None] = mapped_column(String(16))  # approved|rejected|changes_requested
    comment: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    context: Mapped[dict | None] = mapped_column(JSON)
