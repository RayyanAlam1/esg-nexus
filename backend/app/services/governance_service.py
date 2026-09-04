"""Governance service: runs Governance-as-Code rules over metric values, AI outputs and reports,
turning outcomes into Issues (criticality engine) and hard blocks."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import GovernanceBlockedError
from app.engines import rules as rules_engine
from app.engines.readiness import compute as compute_readiness
from app.models.esg import MetricDefinition, MetricValue
from app.models.governance import Issue
from app.models.organization import Entity, ReportingPeriod
from app.models.reporting import Report, ReportSection

CATEGORY_BY_ACTION = {
    "REQUIRE_EVIDENCE": "evidence_gap",
    "BLOCK_REPORT_GENERATION": "governance",
    "BLOCK": "governance",
    "WARN": "data_missing",
    "REQUIRE_HUMAN_REVIEW": "data_quality",
    "REQUIRE_APPROVAL": "approval",
    "ESCALATE": "governance",
    "PREVENT_DATA_MODIFICATION": "governance",
}


def run_metric_rules(db: Session, tenant_id: int, organization_id: int, period: ReportingPeriod) -> dict[str, Any]:
    """Evaluate metric_value-scope rules for every value in the period plus every KPI at group level."""
    rules = rules_engine.active_rules(db, tenant_id, "metric_value")
    entities = {e.id: e for e in db.execute(select(Entity).where(Entity.organization_id == organization_id)).scalars().all()}
    metrics = {m.id: m for m in db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == tenant_id, MetricDefinition.is_active.is_(True))).scalars().all()}
    values = db.execute(select(MetricValue).where(MetricValue.period_id == period.id, MetricValue.entity_id.in_(list(entities)))).scalars().all() if entities else []
    seen: set[tuple[int, int]] = set()
    triggered: list[dict] = []
    fingerprints: set[str] = set()
    evaluated = 0

    def _apply(metric: MetricDefinition, entity: Entity, mv: MetricValue | None):
        nonlocal evaluated
        ctx = rules_engine.metric_value_context(db, metric, entity, period, mv)
        for outcome in rules_engine.evaluate_rules(rules, ctx):
            evaluated += 1
            if not outcome.triggered:
                continue
            issue = rules_engine.upsert_issue(
                db,
                tenant_id,
                outcome=outcome,
                category=CATEGORY_BY_ACTION.get(outcome.action, "governance"),
                title=outcome.message or f"Rule {outcome.rule_code} triggered for {metric.code}",
                metric_code=metric.code,
                entity_code=entity.code,
                period_code=period.code,
            )
            fingerprints.add(issue.fingerprint)
            triggered.append({"issue": issue.code, "rule": outcome.rule_code, "severity": outcome.severity, "action": outcome.action, "metric": metric.code, "entity": entity.code})

    for mv in values:
        metric, entity = metrics.get(mv.metric_id), entities.get(mv.entity_id)
        if metric is None or entity is None:
            continue
        seen.add((metric.id, entity.id))
        _apply(metric, entity, mv)
    group = next((e for e in entities.values() if e.kind == "group"), None)
    if group is not None:
        for metric in metrics.values():
            if metric.is_kpi and (metric.id, group.id) not in seen:
                _apply(metric, group, None)
    resolved = rules_engine.resolve_stale(db, tenant_id, fingerprints, "evidence_gap")
    resolved += rules_engine.resolve_stale(db, tenant_id, fingerprints, "data_missing")
    db.flush()
    return {"rules_evaluated": len(rules), "evaluations": evaluated, "issues_triggered": len(triggered), "auto_resolved": resolved, "triggered": triggered}


def check_ai_output(db: Session, tenant_id: int, context: dict[str, Any]) -> list[rules_engine.RuleOutcome]:
    rules = rules_engine.active_rules(db, tenant_id, "ai_output")
    return [o for o in rules_engine.evaluate_rules(rules, context) if o.triggered]


def check_data_change(db: Session, tenant_id: int, *, period: ReportingPeriod, object_type: str, roles: list[str]) -> None:
    """Raise GovernanceBlockedError when a data change is prevented (e.g. approved report for the period)."""
    report = db.execute(select(Report).where(Report.tenant_id == tenant_id, Report.period_id == period.id, Report.status.in_(["approved", "published"]))).scalars().first()
    ctx = {"object_type": object_type, "report_status": report.status if report else None, "period_status": period.status, "user_roles": roles}
    rules = rules_engine.active_rules(db, tenant_id, "data_change")
    for o in rules_engine.evaluate_rules(rules, ctx):
        if o.blocks:
            raise GovernanceBlockedError(
                o.message or "Data modification prevented by governance rule", details={"rule": o.rule_code, "required_action": o.required_action, "severity": o.severity}
            )


def report_context(db: Session, tenant_id: int, report: Report) -> dict[str, Any]:
    period = db.get(ReportingPeriod, report.period_id)
    readiness = compute_readiness(db, tenant_id, report.organization_id, period, framework_codes=report.framework_codes, report=report)
    issues = (
        db.execute(
            select(Issue).where(Issue.tenant_id == tenant_id, Issue.status.in_(["open", "acknowledged"]), (Issue.period_code == period.code) | (Issue.period_code.is_(None)))
        )
        .scalars()
        .all()
    )
    sections = db.execute(select(ReportSection).where(ReportSection.report_id == report.id)).scalars().all()
    return {
        "report": {"status": report.status, "id": report.id},
        "readiness": readiness.overall,
        "blocking_issues": len([i for i in issues if i.blocks_report and i.severity != "CRITICAL"]),
        "critical_issues": len([i for i in issues if i.severity == "CRITICAL"]),
        "high_issues": len([i for i in issues if i.severity == "HIGH"]),
        "unapproved_sections": len([s for s in sections if s.status not in ("approved", "published")]),
        "framework_alignment": readiness.components.get("framework_alignment"),
        "_readiness": readiness,
    }


def check_report(db: Session, tenant_id: int, report: Report) -> dict[str, Any]:
    ctx = report_context(db, tenant_id, report)
    readiness = ctx.pop("_readiness")
    rules = rules_engine.active_rules(db, tenant_id, "report")
    outcomes = [o for o in rules_engine.evaluate_rules(rules, ctx) if o.triggered]
    blocked = [o for o in outcomes if o.blocks]
    return {
        "blocked": bool(blocked),
        "readiness": readiness.__dict__ | {"components": readiness.components},
        "outcomes": [{"rule": o.rule_code, "severity": o.severity, "action": o.action, "message": o.message, "required_action": o.required_action} for o in outcomes],
        "blocking_reasons": [{"rule": o.rule_code, "message": o.message, "required_action": o.required_action} for o in blocked],
        "context": ctx,
    }
