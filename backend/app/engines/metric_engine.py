"""Deterministic, version-controlled ESG Metric Engine.

- Raw metrics are stored values.
- Derived metrics are computed from a formula referencing other metrics with `{CODE}` placeholders
  (`{CODE@prev}` = previous period of the same entity).
- Every execution is recorded as a CalculationRun (inputs, formula, version) — the lineage anchor.
- Aggregation across the organisational hierarchy is delegated to the consolidation engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engines import consolidation
from app.engines.safe_expr import ExpressionError, compile_formula, evaluate
from app.models.esg import CalculationRun, CalculationVersion, MetricDefinition, MetricValue
from app.models.organization import Entity, ReportingPeriod


@dataclass
class CalcResult:
    metric_code: str
    entity_code: str
    period_code: str
    value: float | None
    status: str  # ok|missing_inputs|error|not_derived
    formula: str | None = None
    version: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    message: str | None = None
    run_id: int | None = None


def previous_period(db: Session, period: ReportingPeriod) -> ReportingPeriod | None:
    stmt = (
        select(ReportingPeriod)
        .where(ReportingPeriod.organization_id == period.organization_id, ReportingPeriod.granularity == period.granularity, ReportingPeriod.end_date < period.start_date)
        .order_by(ReportingPeriod.end_date.desc())
    )
    return db.execute(stmt).scalars().first()


def current_formula(db: Session, metric: MetricDefinition) -> tuple[str | None, str]:
    cv = (
        db.execute(
            select(CalculationVersion).where(CalculationVersion.metric_id == metric.id, CalculationVersion.is_current == True)  # noqa: E712
        )
        .scalars()
        .first()
    )
    if cv:
        return cv.formula, cv.version
    return metric.formula, f"{metric.version}.0"


def get_value(db: Session, tenant_id: int, code: str, entity: Entity, period: ReportingPeriod, *, consolidate: bool = True) -> tuple[float | None, int | None]:
    """Value for (metric, entity, period). Falls back to consolidation of children when the entity has none."""
    metric = db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == tenant_id, MetricDefinition.code == code)).scalars().first()
    if metric is None:
        return None, None
    mv = db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == period.id)).scalars().first()
    if mv is not None and mv.value_numeric is not None:
        return mv.value_numeric, mv.id
    if consolidate and metric.aggregation not in ("none",):
        agg = consolidation.aggregate(db, metric, entity, period)
        if agg.value is not None:
            return agg.value, None
    return None, None


def calculate(db: Session, tenant_id: int, metric: MetricDefinition, entity: Entity, period: ReportingPeriod, *, user_id: int | None = None, persist: bool = True) -> CalcResult:
    formula, version = current_formula(db, metric)
    if not formula:
        return CalcResult(metric.code, entity.code, period.code, None, "not_derived", message="Metric has no formula")
    try:
        expr, mapping = compile_formula(formula)
    except Exception as exc:  # pragma: no cover
        return CalcResult(metric.code, entity.code, period.code, None, "error", formula, version, message=str(exc))

    env: dict[str, Any] = {}
    inputs: dict[str, Any] = {}
    missing: list[str] = []
    prev = previous_period(db, period)
    for var, (code, modifier) in mapping.items():
        target_entity, target_period = entity, period
        if modifier == "prev":
            if prev is None:
                missing.append(f"{code}@prev")
                env[var] = None
                continue
            target_period = prev
        elif modifier and modifier.startswith("entity:"):
            ecode = modifier.split(":", 1)[1]
            e = db.execute(select(Entity).where(Entity.tenant_id == tenant_id, Entity.code == ecode)).scalars().first()
            if e is None:
                missing.append(f"{code}@{modifier}")
                env[var] = None
                continue
            target_entity = e
        value, mv_id = get_value(db, tenant_id, code, target_entity, target_period)
        env[var] = value
        inputs[f"{code}" + (f"@{modifier}" if modifier else "")] = {
            "value": value,
            "metric_value_id": mv_id,
            "entity": target_entity.code,
            "period": target_period.code,
        }
        if value is None:
            missing.append(code)

    status, result, message = "ok", None, None
    if missing:
        status, message = "missing_inputs", f"Data unavailable for: {', '.join(sorted(set(missing)))}"
    else:
        try:
            result = evaluate(expr, env)
            if result is not None:
                result = float(result)
        except ExpressionError as exc:
            status, message = "error", str(exc)
        if status == "ok" and result is None:
            status, message = "missing_inputs", "Formula evaluated to null (division by zero or null input)"

    run_id = None
    if persist:
        run = CalculationRun(
            tenant_id=tenant_id,
            metric_id=metric.id,
            entity_id=entity.id,
            period_id=period.id,
            calculation_version=version,
            formula=formula,
            inputs=inputs,
            result=result,
            status=status,
            message=message,
            executed_by=user_id,
        )
        db.add(run)
        db.flush()
        run_id = run.id
        if status == "ok":
            mv = db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == period.id)).scalars().first()
            if mv is None:
                mv = MetricValue(tenant_id=tenant_id, metric_id=metric.id, entity_id=entity.id, period_id=period.id, status="validated", source_type="calculated", unit=metric.unit)
                db.add(mv)
            # A *reported* value (e.g. printed in an assured report) is never overwritten: the run is linked for
            # lineage and the data-quality engine compares reported vs recalculated (consistency check).
            if mv.source_type != "reported":
                mv.value_numeric = result
                mv.source_type = "calculated"
            mv.calculation_run_id = run.id
            db.flush()
    return CalcResult(metric.code, entity.code, period.code, result, status, formula, version, inputs, message, run_id)


def recalculate_all(db: Session, tenant_id: int, organization_id: int, period: ReportingPeriod, *, user_id: int | None = None) -> list[CalcResult]:
    """Recalculate every derived metric for every entity in the organisation for `period`, dependency-ordered."""
    metrics = (
        db.execute(
            select(MetricDefinition).where(MetricDefinition.tenant_id == tenant_id, MetricDefinition.is_active == True, MetricDefinition.formula.isnot(None))  # noqa: E712
        )
        .scalars()
        .all()
    )
    entities = db.execute(select(Entity).where(Entity.organization_id == organization_id, Entity.is_active == True)).scalars().all()  # noqa: E712
    ordered = _topological(metrics)
    results: list[CalcResult] = []
    for metric in ordered:
        for entity in entities:
            # Only compute where at least one input exists for this entity — avoids noise runs for facilities without data
            res = calculate(db, tenant_id, metric, entity, period, user_id=user_id, persist=False)
            if res.status == "ok" or any(i["value"] is not None for i in res.inputs.values()):
                results.append(calculate(db, tenant_id, metric, entity, period, user_id=user_id, persist=True))
    return results


def _topological(metrics: list[MetricDefinition]) -> list[MetricDefinition]:
    by_code = {m.code: m for m in metrics}
    deps = {m.code: {c for c, _ in _placeholders(m.formula) if c in by_code and c != m.code} for m in metrics}
    ordered: list[MetricDefinition] = []
    visited: set[str] = set()

    def visit(code: str, stack: set[str]):
        if code in visited:
            return
        if code in stack:
            raise ValueError(f"Circular formula dependency at {code}")
        stack.add(code)
        for d in deps.get(code, ()):
            visit(d, stack)
        stack.discard(code)
        visited.add(code)
        ordered.append(by_code[code])

    for m in metrics:
        visit(m.code, set())
    return ordered


def _placeholders(formula: str | None):
    from app.engines.safe_expr import extract_placeholders

    return extract_placeholders(formula or "")


def explain(result: CalcResult) -> str:
    """Human-readable explanation of a calculation (used by the Calculation Agent — it explains, it never computes)."""
    if result.status == "not_derived":
        return f"{result.metric_code} is a raw (reported) metric; no formula applies."
    lines = [f"Formula (version {result.version}): {result.formula}"]
    for code, inp in result.inputs.items():
        v = inp["value"]
        lines.append(f"  {code} = {'Data unavailable' if v is None else v} [{inp['entity']}, {inp['period']}]")
    if result.status == "ok":
        lines.append(f"Result: {result.value}")
    else:
        lines.append(f"Status: {result.status} — {result.message}")
    return "\n".join(lines)
