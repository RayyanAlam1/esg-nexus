"""Governance-as-Code rules engine.

A rule = {code, severity, scope, condition, action, ...}. The condition is a safe expression evaluated
against a context built for the scope. Outcomes are turned into Issues by the criticality engine and
into hard blocks (GovernanceBlockedError) when the action requires it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines.safe_expr import ExpressionError, evaluate
from app.models.esg import MetricDefinition, MetricValue
from app.models.governance import GovernanceRule, Issue
from app.models.organization import Entity, ReportingPeriod

BLOCKING_ACTIONS = {"BLOCK", "BLOCK_REPORT_GENERATION", "PREVENT_DATA_MODIFICATION"}
SEVERITY_RANK = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


@dataclass
class RuleOutcome:
    rule_code: str
    severity: str
    action: str
    triggered: bool
    message: str | None = None
    required_action: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def blocks(self) -> bool:
        return self.triggered and self.action in BLOCKING_ACTIONS


def active_rules(db: Session, tenant_id: int, scope: str | None = None) -> list[GovernanceRule]:
    stmt = select(GovernanceRule).where(GovernanceRule.tenant_id == tenant_id, GovernanceRule.is_active.is_(True), GovernanceRule.approval_status == "approved")
    if scope:
        stmt = stmt.where(GovernanceRule.scope == scope)
    return db.execute(stmt.order_by(GovernanceRule.code)).scalars().all()


def evaluate_rules(rules: list[GovernanceRule], context: dict[str, Any]) -> list[RuleOutcome]:
    outcomes: list[RuleOutcome] = []
    for rule in rules:
        try:
            triggered = bool(evaluate(rule.condition, context))
            outcomes.append(
                RuleOutcome(
                    rule.code, rule.severity, rule.action, triggered, _render(rule.message, context) if triggered else None, rule.required_action if triggered else None, context
                )
            )
        except ExpressionError as exc:
            outcomes.append(RuleOutcome(rule.code, rule.severity, rule.action, False, error=str(exc), context=context))
    return outcomes


def _render(template: str | None, ctx: dict[str, Any]) -> str | None:
    if not template:
        return None
    out = template
    flat = _flatten(ctx)
    for k, v in flat.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _flatten(d: dict, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            flat.update(_flatten(v, key + "."))
        else:
            flat[key] = v
    return flat


# --- context builders ------------------------------------------------------------------------
def metric_value_context(
    db: Session, metric: MetricDefinition, entity: Entity, period: ReportingPeriod, mv: MetricValue | None, *, quality: float | None = None, report_status: str | None = None
) -> dict[str, Any]:
    evidence_count = 0
    verified_count = 0
    if mv is not None:
        from app.engines.evidence_resolution import resolve

        evs, _ = resolve(db, metric, entity, period, mv)
        evidence_count = len(evs)
        verified_count = len([e for e in evs if e.verification_status == "verified"])
    return {
        "metric": {
            "code": metric.code,
            "name": metric.name,
            "pillar": metric.pillar,
            "topic": metric.topic_code,
            "kind": metric.kind,
            "evidence_required": metric.evidence_required,
            "is_kpi": metric.is_kpi,
            "assurance_status": metric.assurance_status,
            "materiality_topic": metric.materiality_topic,
        },
        "entity": {"code": entity.code, "kind": entity.kind, "in_boundary": entity.in_reporting_boundary},
        "period": {"code": period.code, "status": period.status},
        "value": mv.value_numeric if mv else None,
        "is_null": mv is None or (mv.value_numeric is None and not mv.value_text),
        "status": mv.status if mv else "missing",
        "reporting_status": mv.status if mv else "missing",
        "source_type": mv.source_type if mv else None,
        "is_estimate": bool(mv.is_estimate) if mv else False,
        "evidence_count": evidence_count,
        "verified_evidence_count": verified_count,
        "quality_score": quality if quality is not None else (mv.quality_score if mv else None),
        "confidence": mv.confidence if mv else None,
        "report_status": report_status,
    }


def upsert_issue(
    db: Session,
    tenant_id: int,
    *,
    outcome: RuleOutcome,
    category: str,
    title: str,
    metric_code: str | None = None,
    entity_code: str | None = None,
    period_code: str | None = None,
    requirement_code: str | None = None,
    description: str | None = None,
) -> Issue:
    fingerprint = hashlib.sha1("|".join([outcome.rule_code, metric_code or "", entity_code or "", period_code or "", requirement_code or ""]).encode()).hexdigest()[:40]
    issue = db.execute(select(Issue).where(Issue.tenant_id == tenant_id, Issue.fingerprint == fingerprint, Issue.status.in_(["open", "acknowledged"]))).scalars().first()
    if issue is None:
        count = db.execute(select(func.count(Issue.id)).where(Issue.tenant_id == tenant_id)).scalar() or 0
        issue = Issue(tenant_id=tenant_id, code=f"ISS-{count + 1:05d}", fingerprint=fingerprint, category=category, severity=outcome.severity, title=title)
        db.add(issue)
    issue.severity = outcome.severity
    issue.title = title
    issue.description = description or outcome.message
    issue.metric_code, issue.entity_code, issue.period_code, issue.requirement_code = metric_code, entity_code, period_code, requirement_code
    issue.rule_code = outcome.rule_code
    issue.required_action = outcome.required_action
    issue.blocks_report = outcome.action in BLOCKING_ACTIONS or outcome.severity == "CRITICAL"
    db.flush()
    return issue


def resolve_stale(db: Session, tenant_id: int, active_fingerprints: set[str], category: str) -> int:
    """Auto-resolve open issues in `category` whose condition no longer holds."""
    stale = (
        db.execute(
            select(Issue).where(
                Issue.tenant_id == tenant_id, Issue.category == category, Issue.status == "open", Issue.fingerprint.notin_(active_fingerprints) if active_fingerprints else True
            )
        )
        .scalars()
        .all()
    )
    for i in stale:
        i.status = "resolved"
        i.resolution_note = "Condition no longer holds (auto-resolved by governance engine)."
    db.flush()
    return len(stale)
