"""Evidence resolution with inheritance.

A value is supported by (in order): evidence linked to the value itself or its metric definition;
for *calculated* values — the evidence of its calculation inputs; for *consolidated* group values —
the evidence of the child entities' values. Derived numbers therefore never appear as false evidence gaps,
while genuinely unsupported raw values still do.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.esg import CalculationRun, MetricDefinition, MetricValue
from app.models.evidence import Evidence, EvidenceLink
from app.models.organization import Entity, ReportingPeriod


def direct_evidence(db: Session, metric_id: int, mv: MetricValue | None) -> list[Evidence]:
    if mv is None:
        links = db.execute(select(EvidenceLink).where(EvidenceLink.metric_id == metric_id, EvidenceLink.metric_value_id.is_(None))).scalars().all()
    else:
        links = (
            db.execute(select(EvidenceLink).where((EvidenceLink.metric_value_id == mv.id) | ((EvidenceLink.metric_id == metric_id) & (EvidenceLink.metric_value_id.is_(None)))))
            .scalars()
            .all()
        )
    ids = {link.evidence_id for link in links}
    return db.execute(select(Evidence).where(Evidence.id.in_(ids))).scalars().all() if ids else []


def resolve(db: Session, metric: MetricDefinition, entity: Entity, period: ReportingPeriod, mv: MetricValue | None = None, *, depth: int = 0) -> tuple[list[Evidence], str]:
    """Return (evidence, how) where how ∈ direct | inherited_inputs | inherited_children | none."""
    if mv is None:
        mv = db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == period.id)).scalars().first()
    found: dict[int, Evidence] = {}
    hows: list[str] = []
    for e in direct_evidence(db, metric.id, mv):
        if e.period_id is None or e.period_id == period.id:
            found[e.id] = e
    value_level = bool(mv) and any(
        link.metric_value_id == mv.id for link in db.execute(select(EvidenceLink).where(EvidenceLink.evidence_id.in_(list(found)) if found else False)).scalars().all()
    )
    if value_level:
        return list(found.values()), "direct"
    if found:
        hows.append("metric_level")
    if depth > 3:
        return list(found.values()), "+".join(hows) or "none"
    # calculated → inputs
    run = None
    if mv is not None and mv.calculation_run_id:
        run = db.get(CalculationRun, mv.calculation_run_id)
    elif mv is not None and mv.source_type == "calculated":
        run = (
            db.execute(
                select(CalculationRun)
                .where(CalculationRun.metric_id == metric.id, CalculationRun.entity_id == entity.id, CalculationRun.period_id == period.id, CalculationRun.status == "ok")
                .order_by(CalculationRun.executed_at.desc())
            )
            .scalars()
            .first()
        )
    if run is not None:
        seen: dict[int, Evidence] = {}
        for code, inp in (run.inputs or {}).items():
            im = db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == metric.tenant_id, MetricDefinition.code == code.split("@")[0])).scalars().first()
            ie = db.execute(select(Entity).where(Entity.tenant_id == metric.tenant_id, Entity.code == inp.get("entity"))).scalars().first()
            ip = db.execute(select(ReportingPeriod).where(ReportingPeriod.organization_id == entity.organization_id, ReportingPeriod.code == inp.get("period"))).scalars().first()
            if im and ie and ip:
                sub, _ = resolve(db, im, ie, ip, depth=depth + 1)
                for e in sub:
                    seen[e.id] = e
        if seen:
            found.update(seen)
            hows.append("inherited_inputs")
    # consolidated → children
    if mv is None or mv.value_numeric is None:
        seen = {}
        for child in db.execute(select(Entity).where(Entity.parent_id == entity.id, Entity.is_active.is_(True))).scalars().all():
            cmv = db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == child.id, MetricValue.period_id == period.id)).scalars().first()
            if cmv is not None or depth < 2:
                sub, _ = resolve(db, metric, child, period, cmv, depth=depth + 1)
                for e in sub:
                    seen[e.id] = e
        if seen:
            found.update(seen)
            hows.append("inherited_children")
    return list(found.values()), "+".join(hows) or "none"


def evidence_codes(db: Session, metric: MetricDefinition, entity: Entity, period: ReportingPeriod, mv: MetricValue | None = None) -> list[str]:
    ev, _ = resolve(db, metric, entity, period, mv)
    return sorted({e.code for e in ev})
