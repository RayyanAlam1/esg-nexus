"""Scope management / consolidation across the organisational hierarchy.

Consolidation methods per entity: full (100 %), proportional (ownership %), equity/excluded (0 %).
Aggregation per metric: sum | avg | weighted_avg | max | last | none.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.esg import MetricDefinition, MetricValue
from app.models.organization import Entity, ReportingPeriod


@dataclass
class AggregateResult:
    value: float | None
    method: str
    contributions: list[dict] = field(default_factory=list)
    coverage: float = 0.0  # share of children with data


def children_of(db: Session, entity: Entity) -> list[Entity]:
    return db.execute(select(Entity).where(Entity.parent_id == entity.id, Entity.is_active == True)).scalars().all()  # noqa: E712


def _factor(entity: Entity) -> float:
    if not entity.in_reporting_boundary or entity.consolidation_method in ("equity", "excluded"):
        return 0.0
    if entity.consolidation_method == "proportional":
        return (entity.ownership_pct or 0) / 100.0
    return 1.0


def aggregate(db: Session, metric: MetricDefinition, entity: Entity, period: ReportingPeriod) -> AggregateResult:
    """Aggregate `metric` for `entity` from its direct children (recursively when a child has no own value)."""
    method = metric.aggregation or "sum"
    if method == "none":
        return AggregateResult(None, method)
    kids = children_of(db, entity)
    if not kids:
        return AggregateResult(None, method)
    contributions: list[dict] = []
    for child in kids:
        mv = db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == child.id, MetricValue.period_id == period.id)).scalars().first()
        value = mv.value_numeric if mv is not None else None
        if value is None:
            sub = aggregate(db, metric, child, period)
            value = sub.value
        if value is None:
            contributions.append({"entity": child.code, "value": None, "factor": _factor(child), "included": False})
            continue
        contributions.append({"entity": child.code, "value": value, "factor": _factor(child), "included": _factor(child) > 0})
    included = [c for c in contributions if c["included"] and c["value"] is not None]
    coverage = len([c for c in contributions if c["value"] is not None]) / len(contributions) if contributions else 0.0
    if not included:
        return AggregateResult(None, method, contributions, coverage)
    if method == "sum":
        val = sum(c["value"] * c["factor"] for c in included)
    elif method == "avg":
        val = sum(c["value"] for c in included) / len(included)
    elif method == "weighted_avg":
        weights = sum(c["factor"] for c in included) or 1.0
        val = sum(c["value"] * c["factor"] for c in included) / weights
    elif method == "max":
        val = max(c["value"] for c in included)
    elif method == "last":
        val = included[-1]["value"]
    else:
        val = None
    return AggregateResult(val, method, contributions, coverage)


def tree(db: Session, organization_id: int) -> list[dict]:
    """Return the entity hierarchy as nested dicts."""
    entities = db.execute(select(Entity).where(Entity.organization_id == organization_id).order_by(Entity.code)).scalars().all()
    by_parent: dict[int | None, list[Entity]] = {}
    for e in entities:
        by_parent.setdefault(e.parent_id, []).append(e)

    def build(parent_id: int | None) -> list[dict]:
        return [
            {
                "id": e.id,
                "code": e.code,
                "name": e.name,
                "kind": e.kind,
                "ownership_pct": e.ownership_pct,
                "consolidation_method": e.consolidation_method,
                "in_reporting_boundary": e.in_reporting_boundary,
                "country": e.country,
                "location": e.location,
                "sector": e.sector,
                "attributes": e.attributes or {},
                "children": build(e.id),
            }
            for e in by_parent.get(parent_id, [])
        ]

    return build(None)
