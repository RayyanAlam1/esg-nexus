"""Report Readiness + Criticality engines.

Readiness = weighted blend of Data Completeness, Data Quality, Evidence Coverage, Framework Alignment,
Governance Checks, AI Evaluation and Human Approvals, penalised by open issues by severity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines import frameworks as fw_engine
from app.models.ai import Evaluation, QualityScore
from app.models.esg import MetricDefinition, MetricValue
from app.models.governance import Approval, Issue
from app.models.organization import Entity, ReportingPeriod
from app.models.reporting import Report, ReportSection

WEIGHTS = {
    "data_completeness": 0.18,
    "data_quality": 0.17,
    "evidence_coverage": 0.17,
    "framework_alignment": 0.16,
    "governance_checks": 0.12,
    "ai_evaluation": 0.08,
    "human_approvals": 0.12,
}
SEVERITY_PENALTY = {"INFO": 0.0, "LOW": 0.2, "MEDIUM": 0.6, "HIGH": 1.5, "CRITICAL": 4.0}


@dataclass
class Readiness:
    components: dict[str, float]
    overall: float
    open_issues: dict[str, int]
    blocking_issues: list[dict]
    explanation: list[str] = field(default_factory=list)
    ready_to_publish: bool = False


def compute(db: Session, tenant_id: int, organization_id: int, period: ReportingPeriod, *, framework_codes: list[str] | None = None, report: Report | None = None) -> Readiness:
    entity_ids = [e.id for e in db.execute(select(Entity).where(Entity.organization_id == organization_id)).scalars().all()]
    metrics = (
        db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == tenant_id, MetricDefinition.is_active.is_(True), MetricDefinition.kind != "narrative"))
        .scalars()
        .all()
    )
    values = db.execute(select(MetricValue).where(MetricValue.period_id == period.id, MetricValue.entity_id.in_(entity_ids))).scalars().all() if entity_ids else []
    explanation: list[str] = []

    # Data completeness: KPIs with a value at group level or any entity
    kpi_codes = [m for m in metrics if m.is_kpi]
    have = {mv.metric_id for mv in values if mv.value_numeric is not None or mv.value_text}
    completeness = (len([m for m in kpi_codes if m.id in have]) / len(kpi_codes) * 100) if kpi_codes else 0.0
    explanation.append(f"Data completeness: {len([m for m in kpi_codes if m.id in have])} of {len(kpi_codes)} KPIs have values for {period.code}.")

    # Data quality: mean of quality scores for the period
    q = db.execute(select(func.avg(QualityScore.overall)).where(QualityScore.period_id == period.id, QualityScore.entity_id.in_(entity_ids))).scalar() if entity_ids else None
    quality = float(q) if q is not None else 0.0
    explanation.append(f"Data quality: average quality score {quality:.1f}.")

    # Evidence coverage: values with evidence_required that have ≥1 evidence link
    req_values = [mv for mv in values if db.get(MetricDefinition, mv.metric_id).evidence_required]
    from app.engines.evidence_resolution import evidence_codes

    covered = 0
    for mv in req_values:
        if evidence_codes(db, db.get(MetricDefinition, mv.metric_id), db.get(Entity, mv.entity_id), period, mv):
            covered += 1
    evidence_cov = covered / len(req_values) * 100 if req_values else 0.0
    explanation.append(f"Evidence coverage: {covered} of {len(req_values)} evidence-required values are linked to evidence.")

    # Framework alignment
    alignment = 0.0
    if framework_codes:
        scores = [fw_engine.coverage(db, tenant_id, organization_id, period, code)["alignment_pct"] for code in framework_codes]
        alignment = sum(scores) / len(scores) if scores else 0.0
        explanation.append(f"Framework alignment across {', '.join(framework_codes)}: {alignment:.1f}%.")
    else:
        explanation.append("Framework alignment: no frameworks selected.")

    # Governance checks: 100 − penalties from open issues
    issues = (
        db.execute(
            select(Issue).where(Issue.tenant_id == tenant_id, Issue.status.in_(["open", "acknowledged"]), (Issue.period_code == period.code) | (Issue.period_code.is_(None)))
        )
        .scalars()
        .all()
    )
    open_counts = {s: 0 for s in SEVERITY_PENALTY}
    for i in issues:
        open_counts[i.severity] = open_counts.get(i.severity, 0) + 1
    penalty = sum(SEVERITY_PENALTY[s] * n for s, n in open_counts.items())
    governance = max(0.0, 100.0 - penalty)
    explanation.append(f"Governance checks: {len(issues)} open issue(s) → penalty {penalty:.1f}.")

    # AI evaluation: mean of AI evaluations in period (report sections / agent runs)
    ai_avg = db.execute(select(func.avg(Evaluation.overall)).where(Evaluation.tenant_id == tenant_id, Evaluation.dimension == "ai")).scalar()
    ai_eval = float(ai_avg) if ai_avg is not None else 100.0
    explanation.append(f"AI evaluation: mean score {ai_eval:.1f} ({'no AI outputs evaluated yet' if ai_avg is None else 'evaluated outputs'}).")

    # Human approvals: approved report sections / all sections
    approvals = 100.0
    if report is not None:
        sections = db.execute(select(ReportSection).where(ReportSection.report_id == report.id)).scalars().all()
        if sections:
            approved = len([s for s in sections if s.status in ("approved", "published")])
            approvals = approved / len(sections) * 100
            explanation.append(f"Human approvals: {approved} of {len(sections)} report sections approved.")
    else:
        pending = db.execute(select(func.count(Approval.id)).where(Approval.tenant_id == tenant_id, Approval.decision.is_(None))).scalar() or 0
        approvals = max(0.0, 100.0 - pending * 5)
        explanation.append(f"Human approvals: {pending} pending approval request(s).")

    components = {
        "data_completeness": round(completeness, 1),
        "data_quality": round(quality, 1),
        "evidence_coverage": round(evidence_cov, 1),
        "framework_alignment": round(alignment, 1),
        "governance_checks": round(governance, 1),
        "ai_evaluation": round(ai_eval, 1),
        "human_approvals": round(approvals, 1),
    }
    overall = round(sum(components[k] * w for k, w in WEIGHTS.items()), 1)
    blocking = [
        {"code": i.code, "severity": i.severity, "title": i.title, "required_action": i.required_action, "metric_code": i.metric_code, "entity_code": i.entity_code}
        for i in issues
        if i.blocks_report
    ]
    ready = not blocking and overall >= 80
    return Readiness(components, overall, open_counts, blocking, explanation, ready)
