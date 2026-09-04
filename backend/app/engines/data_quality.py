"""Data Quality Engine.

Scores each (metric, entity, period) on completeness, accuracy, consistency, timeliness, validity,
uniqueness and traceability, and explains every deduction. Scores are 0–100.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engines.metric_engine import previous_period
from app.models.ai import QualityScore
from app.models.esg import CalculationRun, MetricDefinition, MetricValue
from app.models.evidence import Evidence
from app.models.organization import Entity, ReportingPeriod

WEIGHTS = {"completeness": 0.2, "accuracy": 0.2, "consistency": 0.15, "timeliness": 0.1, "validity": 0.15, "uniqueness": 0.05, "traceability": 0.15}


@dataclass
class QualityResult:
    metric_code: str
    entity_code: str
    period_code: str
    scores: dict[str, float]
    overall: float
    explanation: list[str] = field(default_factory=list)


def _evidence_for(db: Session, mv: MetricValue) -> list[Evidence]:
    from app.engines.evidence_resolution import resolve

    metric = db.get(MetricDefinition, mv.metric_id)
    entity = db.get(Entity, mv.entity_id)
    period = db.get(ReportingPeriod, mv.period_id)
    ev, _ = resolve(db, metric, entity, period, mv)
    return ev


def assess(db: Session, tenant_id: int, metric: MetricDefinition, entity: Entity, period: ReportingPeriod, *, persist: bool = True) -> QualityResult:
    mv = db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == period.id)).scalars().first()
    notes: list[str] = []
    scores = {k: 100.0 for k in WEIGHTS}

    # Completeness
    if mv is None or (mv.value_numeric is None and not mv.value_text):
        scores["completeness"] = 0.0
        notes.append("No value recorded for this period (Data unavailable).")
        for k in ("accuracy", "consistency", "timeliness", "validity", "uniqueness", "traceability"):
            scores[k] = 0.0
        overall = 0.0
        result = QualityResult(metric.code, entity.code, period.code, scores, overall, notes)
        if persist:
            _persist(db, tenant_id, metric, entity, period, result)
        return result

    if mv.is_estimate:
        scores["accuracy"] -= 25
        notes.append("Value is flagged as an estimate (-25 accuracy).")
    if mv.confidence is not None and mv.confidence < 0.9:
        deduction = round((0.9 - mv.confidence) * 100)
        scores["accuracy"] = max(0.0, scores["accuracy"] - deduction)
        notes.append(f"Recorded confidence {mv.confidence:.2f} (-{deduction} accuracy).")

    # Validity: validation rules
    rules = metric.validation_rules or {}
    v = mv.value_numeric
    if v is not None:
        if "min" in rules and v < rules["min"]:
            scores["validity"] = 0.0
            notes.append(f"Value {v} below minimum {rules['min']}.")
        if "max" in rules and v > rules["max"]:
            scores["validity"] = 0.0
            notes.append(f"Value {v} above maximum {rules['max']}.")
        if metric.data_type == "integer" and float(v).is_integer() is False:
            scores["validity"] -= 30
            notes.append("Non-integer value for an integer metric.")
        if metric.data_type == "percentage" and not (0 <= v <= 100) and "max" not in rules:
            scores["validity"] -= 40
            notes.append("Percentage outside 0–100.")
    elif metric.data_type not in ("text", "boolean"):
        scores["validity"] -= 20
        notes.append("Numeric metric stored as text only.")

    # Consistency: YoY change vs. threshold, and reported-vs-calculated agreement
    prev = previous_period(db, period)
    if prev is not None and v is not None:
        pmv = db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == prev.id)).scalars().first()
        if pmv is not None and pmv.value_numeric not in (None, 0):
            change = abs(v - pmv.value_numeric) / abs(pmv.value_numeric) * 100
            limit = rules.get("max_yoy_change_pct", 50)
            if change > limit:
                scores["consistency"] -= 30
                notes.append(f"Year-over-year change {change:.1f}% exceeds {limit}% threshold — review for anomaly.")
    if mv.source_type == "reported" and metric.formula:
        run = (
            db.execute(
                select(CalculationRun)
                .where(CalculationRun.metric_id == metric.id, CalculationRun.entity_id == entity.id, CalculationRun.period_id == period.id, CalculationRun.status == "ok")
                .order_by(CalculationRun.executed_at.desc())
            )
            .scalars()
            .first()
        )
        if run is not None and run.result is not None and v is not None:
            tol = rules.get("tolerance_pct", 1.0)
            diff = abs(run.result - v) / abs(v) * 100 if v else abs(run.result - v)
            if diff > tol:
                scores["consistency"] -= 40
                scores["accuracy"] -= 20
                notes.append(f"Reported value {v} differs from recalculated {run.result:.4g} by {diff:.2f}% (tolerance {tol}%).")
            else:
                notes.append(f"Reported value agrees with recalculation ({diff:.3f}% difference).")

    # Timeliness: reference date = earliest linked evidence date for reported values, else record creation
    ev = _evidence_for(db, mv)
    ref_date = min([e.evidence_date for e in ev if e.evidence_date], default=None) if mv.source_type == "reported" and ev else None
    ref_date = ref_date or (mv.created_at.date() if mv.created_at is not None else None)
    if mv.source_type == "calculated":
        ref_date = None  # calculated values inherit timeliness from their inputs
    if ref_date is not None:
        days_late = (ref_date - period.end_date).days
        if days_late > 365:
            scores["timeliness"] -= 30
            notes.append("Value recorded more than 12 months after period end.")

    # Uniqueness: duplicate dataset records for the same key
    dup = db.execute(select(func.count(MetricValue.id)).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == period.id)).scalar()
    if dup and dup > 1:  # pragma: no cover - prevented by unique constraint
        scores["uniqueness"] = 0.0

    # Traceability: evidence + lineage
    if metric.evidence_required:
        if not ev:
            scores["traceability"] = 0.0
            notes.append("Evidence required but none linked (Evidence required).")
        else:
            verified = [e for e in ev if e.verification_status == "verified"]
            if not verified:
                scores["traceability"] -= 40
                notes.append(f"{len(ev)} evidence item(s) linked but none verified.")
            else:
                notes.append(f"{len(verified)} verified evidence item(s) linked.")
    if mv.source_type == "calculated" and mv.calculation_run_id is None:
        scores["traceability"] -= 30
        notes.append("Calculated value without a calculation run.")
    if mv.source_type == "manual" and mv.dataset_version_id is None:
        scores["traceability"] -= 10
        notes.append("Manual entry without a source dataset.")

    scores = {k: max(0.0, min(100.0, round(s, 1))) for k, s in scores.items()}
    overall = round(sum(scores[k] * w for k, w in WEIGHTS.items()), 1)
    result = QualityResult(metric.code, entity.code, period.code, scores, overall, notes)
    if persist:
        _persist(db, tenant_id, metric, entity, period, result)
        mv.quality_score = overall
    return result


def _persist(db: Session, tenant_id: int, metric: MetricDefinition, entity: Entity, period: ReportingPeriod, result: QualityResult) -> None:
    qs = db.execute(select(QualityScore).where(QualityScore.metric_id == metric.id, QualityScore.entity_id == entity.id, QualityScore.period_id == period.id)).scalars().first()
    if qs is None:
        qs = QualityScore(tenant_id=tenant_id, metric_id=metric.id, entity_id=entity.id, period_id=period.id)
        db.add(qs)
    for k, v in result.scores.items():
        setattr(qs, k, v)
    qs.overall = result.overall
    qs.explanation = result.explanation
    db.flush()


def assess_all(db: Session, tenant_id: int, organization_id: int, period: ReportingPeriod) -> list[QualityResult]:
    results = []
    values = (
        db.execute(select(MetricValue).join(Entity, Entity.id == MetricValue.entity_id).where(MetricValue.period_id == period.id, Entity.organization_id == organization_id))
        .scalars()
        .all()
    )
    for mv in values:
        metric = db.get(MetricDefinition, mv.metric_id)
        entity = db.get(Entity, mv.entity_id)
        results.append(assess(db, tenant_id, metric, entity, period))
    return results


def dataset_quality(records: list[dict], expected_fields: list[str]) -> dict:
    """Quality summary for an ingested dataset (used by the ingestion pipeline)."""
    n = len(records) or 1
    complete = sum(1 for r in records if all(r.get(f) not in (None, "") for f in expected_fields))
    valid = sum(1 for r in records if r.get("_valid", True))
    keys = [(r.get("metric_code"), r.get("entity_code"), r.get("period_code")) for r in records]
    unique = len(set(keys))
    return {
        "completeness": round(complete / n * 100, 1),
        "validity": round(valid / n * 100, 1),
        "uniqueness": round(unique / n * 100, 1),
        "rows": len(records),
    }
