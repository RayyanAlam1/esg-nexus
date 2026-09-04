"""ESG intelligence endpoints: executive overview and pillar dashboards."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import DB, User, get_entity, get_org, get_period, serialize
from app.engines import metric_engine
from app.engines.readiness import compute as compute_readiness
from app.models.ai import QualityScore
from app.models.esg import EsgTopic, MetricDefinition, MetricValue, Target
from app.models.governance import Issue
from app.models.organization import Entity, ReportingPeriod

router = APIRouter(prefix="/esg", tags=["esg"])

OVERVIEW_KPIS = [
    "ENV.GHG.SCOPE1_2_TOTAL",
    "ENV.GHG.INTENSITY_REVENUE",
    "ENV.ENERGY.TOTAL",
    "ENV.WATER.WITHDRAWN",
    "ENV.WASTE.TOTAL",
    "SOC.WORKFORCE.TOTAL",
    "SOC.DEI.PERM_FEMALE_PCT",
    "SOC.OHS.TRIR_EMP",
    "SOC.OHS.TRIR_CONTRACTOR",
    "SOC.WORKFORCE.TURNOVER_RATE_PCT",
    "GOV.BOARD.INDEPENDENCE_PCT",
    "GOV.ETHICS.CORRUPTION_CASES_SUBSTANTIATED",
    "ECO.FIN.REVENUE",
    "ECO.EVGD.WEALTH_GENERATED",
    "ECO.TAX.TOTAL",
    "SOC.COMMUNITY.INVESTMENT_PKR_MN",
]


def kpi_card(db, principal, metric: MetricDefinition, entity: Entity, period: ReportingPeriod) -> dict:
    cur, mv_id = metric_engine.get_value(db, principal.tenant_id, metric.code, entity, period)
    prev_p = metric_engine.previous_period(db, period)
    prev, _ = metric_engine.get_value(db, principal.tenant_id, metric.code, entity, prev_p) if prev_p else (None, None)
    yoy = ((cur - prev) / abs(prev) * 100) if cur is not None and prev not in (None, 0) else None
    target = db.execute(select(Target).where(Target.metric_id == metric.id, Target.entity_id == entity.id)).scalars().first()
    mv = db.get(MetricValue, mv_id) if mv_id else None
    from app.engines.evidence_resolution import evidence_codes

    ev_count = len(evidence_codes(db, metric, entity, period, mv)) if cur is not None else 0
    qs = db.execute(select(QualityScore).where(QualityScore.metric_id == metric.id, QualityScore.entity_id == entity.id, QualityScore.period_id == period.id)).scalars().first()
    issues = db.execute(select(func.count(Issue.id)).where(Issue.metric_code == metric.code, Issue.status.in_(["open", "acknowledged"]))).scalar()
    status = "no_target"
    if target and target.target_value is not None and cur is not None:
        if target.direction == "decrease":
            status = "on_track" if cur <= target.target_value else "above_target"
        elif target.direction == "increase":
            status = "on_track" if cur >= target.target_value else "below_target"
        else:
            status = "on_track" if abs(cur - target.target_value) < 1e-9 else "off_target"
    elif target and target.status == "not_set":
        status = "target_not_set"
    trend = "flat"
    if yoy is not None:
        good = metric.direction == "higher_is_better"
        trend = (
            ("improving" if (yoy > 0) == good else "worsening")
            if abs(yoy) > 0.5 and metric.direction in ("higher_is_better", "lower_is_better")
            else ("up" if yoy > 0 else "down" if yoy < 0 else "flat")
        )
    return {
        "code": metric.code,
        "name": metric.name,
        "unit": metric.unit,
        "pillar": metric.pillar,
        "topic": metric.topic_code,
        "kind": metric.kind,
        "direction": metric.direction,
        "value": cur,
        "previous": prev,
        "yoy_pct": round(yoy, 2) if yoy is not None else None,
        "trend": trend,
        "period": period.code,
        "previous_period": prev_p.code if prev_p else None,
        "target": {"value": target.target_value, "year": target.target_year, "direction": target.direction, "status": target.status} if target else None,
        "target_status": status,
        "data_unavailable": cur is None,
        "source_type": mv.source_type if mv else ("consolidated" if cur is not None else None),
        "is_estimate": bool(mv.is_estimate) if mv else False,
        "evidence_count": ev_count,
        "quality_score": qs.overall if qs else (mv.quality_score if mv else None),
        "open_issues": issues,
        "assurance_status": metric.assurance_status,
        "is_kpi": metric.is_kpi,
    }


@router.get("/overview")
def overview(principal: User, db: DB, period: str | None = None, entity: str | None = None, org_id: int | None = None):
    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    e = get_entity(db, principal, org, entity)
    metrics = {
        m.code: m for m in db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == principal.tenant_id, MetricDefinition.code.in_(OVERVIEW_KPIS))).scalars().all()
    }
    cards = [kpi_card(db, principal, metrics[c], e, p) for c in OVERVIEW_KPIS if c in metrics]
    rd = compute_readiness(db, principal.tenant_id, org.id, p, framework_codes=["WEF_SCM", "UNGC", "UN_SDG"])
    issues = (
        db.execute(select(Issue).where(Issue.tenant_id == principal.tenant_id, Issue.status.in_(["open", "acknowledged"])).order_by(Issue.severity.desc(), Issue.id))
        .scalars()
        .all()
    )
    sev_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    issues = sorted(issues, key=lambda i: sev_rank.get(i.severity, 5))
    n_values = db.execute(select(func.count(MetricValue.id)).where(MetricValue.period_id == p.id)).scalar()
    n_metrics = db.execute(select(func.count(MetricDefinition.id)).where(MetricDefinition.tenant_id == principal.tenant_id, MetricDefinition.is_active.is_(True))).scalar()
    return {
        "organization": serialize(org),
        "period": serialize(p),
        "entity": {"code": e.code, "name": e.name},
        "readiness": {
            "overall": rd.overall,
            "components": rd.components,
            "open_issues": rd.open_issues,
            "blocking_issues": rd.blocking_issues,
            "explanation": rd.explanation,
            "ready_to_publish": rd.ready_to_publish,
        },
        "kpis": cards,
        "issues": {
            "total": len(issues),
            "critical": len([i for i in issues if i.severity == "CRITICAL"]),
            "high": len([i for i in issues if i.severity == "HIGH"]),
            "top": serialize(issues[:8]),
        },
        "coverage": {"metric_definitions": n_metrics, "values_in_period": n_values},
        "what_changed": [c for c in cards if c["yoy_pct"] is not None and abs(c["yoy_pct"]) >= 5][:8],
    }


@router.get("/topics")
def topics(principal: User, db: DB):
    tps = db.execute(select(EsgTopic).where(EsgTopic.tenant_id == principal.tenant_id).order_by(EsgTopic.sort_order)).scalars().all()
    return [{**serialize(t), "subtopics": serialize(t.subtopics)} for t in tps]


@router.get("/pillar/{pillar}")
def pillar(pillar: str, principal: User, db: DB, period: str | None = None, entity: str | None = None, org_id: int | None = None, kpi_only: bool = False):
    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    e = get_entity(db, principal, org, entity)
    tps = db.execute(select(EsgTopic).where(EsgTopic.tenant_id == principal.tenant_id, EsgTopic.pillar == pillar).order_by(EsgTopic.sort_order)).scalars().all()
    out_topics = []
    for t in tps:
        stmt = select(MetricDefinition).where(MetricDefinition.tenant_id == principal.tenant_id, MetricDefinition.topic_code == t.code, MetricDefinition.is_active.is_(True))
        if kpi_only:
            stmt = stmt.where(MetricDefinition.is_kpi.is_(True))
        ms = db.execute(stmt.order_by(MetricDefinition.is_kpi.desc(), MetricDefinition.code)).scalars().all()
        cards = [kpi_card(db, principal, m, e, p) for m in ms if m.kind != "narrative"]
        narratives = []
        for m in ms:
            if m.kind == "narrative":
                mv = db.execute(select(MetricValue).where(MetricValue.metric_id == m.id, MetricValue.entity_id == e.id, MetricValue.period_id == p.id)).scalars().first()
                narratives.append({"code": m.code, "name": m.name, "text": mv.value_text if mv else None, "data_unavailable": mv is None})
        out_topics.append({"code": t.code, "name": t.name, "description": t.description, "metrics": cards, "narratives": narratives, "kpis": [c for c in cards if c["is_kpi"]]})
    return {"pillar": pillar, "period": serialize(p), "entity": {"code": e.code, "name": e.name}, "topics": out_topics}


@router.get("/entity-comparison")
def entity_comparison(principal: User, db: DB, metric: str, period: str | None = None, org_id: int | None = None):
    """Values of one metric across all entities (drill-down / comparison charts)."""
    from app.api.deps import get_metric

    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    m = get_metric(db, principal, metric)
    prev = metric_engine.previous_period(db, p)
    out = []
    for ent in db.execute(select(Entity).where(Entity.organization_id == org.id).order_by(Entity.code)).scalars().all():
        if principal.entity_ids and ent.id not in principal.entity_ids:
            continue  # business-unit scoped users only see their entities
        cur = db.execute(select(MetricValue).where(MetricValue.metric_id == m.id, MetricValue.entity_id == ent.id, MetricValue.period_id == p.id)).scalars().first()
        pv = (
            db.execute(select(MetricValue).where(MetricValue.metric_id == m.id, MetricValue.entity_id == ent.id, MetricValue.period_id == prev.id)).scalars().first()
            if prev
            else None
        )
        if cur is None and pv is None:
            continue
        out.append(
            {
                "entity": ent.code,
                "name": ent.name,
                "kind": ent.kind,
                "value": cur.value_numeric if cur else None,
                "previous": pv.value_numeric if pv else None,
                "consolidation": ent.consolidation_method,
                "in_boundary": ent.in_reporting_boundary,
            }
        )
    return {"metric": {"code": m.code, "name": m.name, "unit": m.unit}, "period": p.code, "previous_period": prev.code if prev else None, "entities": out}
