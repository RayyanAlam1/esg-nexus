"""Metric library, KPI tracking, interactive metric detail, calculations, targets, lineage."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, Page, User, get_entity, get_metric, get_org, get_period, paginate, serialize
from app.api.v1.esg import kpi_card
from app.core import audit
from app.core.security import require
from app.engines import data_quality, lineage, metric_engine
from app.engines.rules import active_rules, evaluate_rules, metric_value_context
from app.models.ai import QualityScore
from app.models.audit import AuditLog
from app.models.esg import CalculationRun, CalculationVersion, MetricDefinition, MetricValue, Target
from app.models.evidence import Evidence, EvidenceLink
from app.models.frameworks import Framework, FrameworkVersion, Requirement
from app.models.governance import Issue
from app.models.organization import Entity, ReportingPeriod
from app.services.governance_service import check_data_change, run_metric_rules

router = APIRouter(prefix="/metrics", tags=["metrics"])


class MetricIn(BaseModel):
    code: str
    name: str
    pillar: str
    topic_code: str
    subtopic_code: str | None = None
    unit: str | None = None
    data_type: str = "decimal"
    kind: str = "raw"
    formula: str | None = None
    description: str | None = None
    calculation_method: str | None = None
    evidence_required: bool = True
    applicable_frameworks: list[str] = []
    materiality_topic: str | None = None
    validation_rules: dict | None = None
    aggregation: str = "sum"
    direction: str | None = None
    is_kpi: bool = False
    assurance_status: str = "not_assured"


class ValueIn(BaseModel):
    entity_code: str | None = None
    period_code: str
    value_numeric: float | None = None
    value_text: str | None = None
    is_estimate: bool = False
    confidence: float | None = None
    notes: str | None = None
    reason: str | None = None
    evidence_codes: list[str] = []


class TargetIn(BaseModel):
    metric_code: str
    entity_code: str | None = None
    target_value: float | None = None
    baseline_value: float | None = None
    target_year: int | None = None
    direction: str = "decrease"
    kind: str = "absolute"
    description: str | None = None
    status: str = "active"


class FormulaIn(BaseModel):
    formula: str
    version: str
    description: str | None = None


@router.get("")
def list_metrics(
    principal: User,
    db: DB,
    page: Page = Depends(),
    pillar: str | None = None,
    topic: str | None = None,
    kpi: bool | None = None,
    q: str | None = None,
    kind: str | None = None,
    framework: str | None = None,
):
    stmt = select(MetricDefinition).where(MetricDefinition.tenant_id == principal.tenant_id, MetricDefinition.is_active.is_(True))
    if pillar:
        stmt = stmt.where(MetricDefinition.pillar == pillar)
    if topic:
        stmt = stmt.where(MetricDefinition.topic_code == topic)
    if kpi is not None:
        stmt = stmt.where(MetricDefinition.is_kpi == kpi)
    if kind:
        stmt = stmt.where(MetricDefinition.kind == kind)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(MetricDefinition.name.ilike(like) | MetricDefinition.code.ilike(like) | MetricDefinition.description.ilike(like))
    if framework:
        stmt = stmt.where(MetricDefinition.applicable_frameworks.cast(__import__("sqlalchemy").String).ilike(f"%{framework}%"))
    if not page.sort:
        stmt = stmt.order_by(MetricDefinition.pillar, MetricDefinition.topic_code, MetricDefinition.is_kpi.desc(), MetricDefinition.code)
    return paginate(db, stmt, page, MetricDefinition)


@router.post("", dependencies=[Depends(require("metric.write"))])
def create_metric(body: MetricIn, principal: User, db: DB):
    m = MetricDefinition(tenant_id=principal.tenant_id, **body.model_dump())
    db.add(m)
    db.flush()
    if body.formula:
        db.add(
            CalculationVersion(
                tenant_id=principal.tenant_id,
                metric_id=m.id,
                version="1.0",
                formula=body.formula,
                description=body.calculation_method,
                is_current=True,
                approved_by=principal.user_id,
            )
        )
    audit.record(
        db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="metric.create", object_type="metric_definition", object_id=m.code, new_value=body.model_dump()
    )
    db.commit()
    return serialize(m)


@router.get("/kpis")
def kpis(principal: User, db: DB, period: str | None = None, entity: str | None = None, pillar: str | None = None, org_id: int | None = None):
    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    e = get_entity(db, principal, org, entity)
    stmt = select(MetricDefinition).where(MetricDefinition.tenant_id == principal.tenant_id, MetricDefinition.is_kpi.is_(True), MetricDefinition.is_active.is_(True))
    if pillar:
        stmt = stmt.where(MetricDefinition.pillar == pillar)
    ms = db.execute(stmt.order_by(MetricDefinition.pillar, MetricDefinition.code)).scalars().all()
    return {"period": p.code, "entity": e.code, "kpis": [kpi_card(db, principal, m, e, p) for m in ms]}


@router.get("/{code}")
def metric_definition(code: str, principal: User, db: DB):
    m = get_metric(db, principal, code)
    versions = db.execute(select(CalculationVersion).where(CalculationVersion.metric_id == m.id).order_by(CalculationVersion.version)).scalars().all()
    return {**serialize(m), "calculation_versions": serialize(versions), "framework_requirements": _requirements_for(db, m)}


def _requirements_for(db, m: MetricDefinition) -> list[dict]:
    out = []
    for code in m.applicable_frameworks or []:
        req = db.execute(select(Requirement).where(Requirement.code == code)).scalars().first()
        if req:
            fv = db.get(FrameworkVersion, req.framework_version_id)
            fw = db.get(Framework, fv.framework_id)
            out.append(
                {
                    "code": req.code,
                    "title": req.title,
                    "framework": fw.code,
                    "framework_name": fw.name,
                    "version": fv.version,
                    "pillar": req.pillar,
                    "disclosure_type": req.disclosure_type,
                }
            )
        else:
            out.append({"code": code, "title": None, "framework": code.split(".")[0]})
    return out


@router.get("/{code}/detail")
def metric_detail(code: str, principal: User, db: DB, entity: str | None = None, period: str | None = None, org_id: int | None = None):
    """Interactive metric detail: value, trend, calculation, inputs, sources, evidence, mapping, quality, governance, audit."""
    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    e = get_entity(db, principal, org, entity)
    m = get_metric(db, principal, code)
    card = kpi_card(db, principal, m, e, p)
    periods = db.execute(select(ReportingPeriod).where(ReportingPeriod.organization_id == org.id).order_by(ReportingPeriod.start_date)).scalars().all()
    series = []
    for per in periods:
        v, mv_id = metric_engine.get_value(db, principal.tenant_id, m.code, e, per)
        mv = db.get(MetricValue, mv_id) if mv_id else None
        series.append(
            {
                "period": per.code,
                "value": v,
                "status": mv.status if mv else ("consolidated" if v is not None else "unavailable"),
                "source_type": mv.source_type if mv else None,
                "text": mv.value_text if mv else None,
            }
        )
    mv = db.execute(select(MetricValue).where(MetricValue.metric_id == m.id, MetricValue.entity_id == e.id, MetricValue.period_id == p.id)).scalars().first()
    calc = None
    if m.formula:
        res = metric_engine.calculate(db, principal.tenant_id, m, e, p, persist=False)
        calc = {
            "formula": res.formula,
            "version": res.version,
            "status": res.status,
            "result": res.value,
            "inputs": res.inputs,
            "message": res.message,
            "explanation": metric_engine.explain(res),
        }
    from app.engines.evidence_resolution import resolve

    evs, how = resolve(db, m, e, p, mv)
    evidence = [{**serialize(ev, exclude={"excerpt"}), "excerpt": (ev.excerpt or "")[:500], "relation": "supports", "resolution": how} for ev in evs]
    qs = db.execute(select(QualityScore).where(QualityScore.metric_id == m.id, QualityScore.entity_id == e.id, QualityScore.period_id == p.id)).scalars().first()
    if qs is None and mv is not None:
        r = data_quality.assess(db, principal.tenant_id, m, e, p, persist=False)
        quality = {"scores": r.scores, "overall": r.overall, "explanation": r.explanation}
    else:
        quality = (
            {
                "scores": {k: getattr(qs, k) for k in ("completeness", "accuracy", "consistency", "timeliness", "validity", "uniqueness", "traceability")},
                "overall": qs.overall,
                "explanation": qs.explanation,
            }
            if qs
            else None
        )
    ctx = metric_value_context(db, m, e, p, mv)
    gov = [
        {"rule": o.rule_code, "severity": o.severity, "action": o.action, "message": o.message, "required_action": o.required_action}
        for o in evaluate_rules(active_rules(db, principal.tenant_id, "metric_value"), ctx)
        if o.triggered
    ]
    issues = db.execute(select(Issue).where(Issue.tenant_id == principal.tenant_id, Issue.metric_code == m.code, Issue.status.in_(["open", "acknowledged"]))).scalars().all()
    targets = db.execute(select(Target).where(Target.metric_id == m.id)).scalars().all()
    history = (
        db.execute(select(AuditLog).where(AuditLog.tenant_id == principal.tenant_id, AuditLog.object_id.like(f"{m.code}%")).order_by(AuditLog.created_at.desc()).limit(20))
        .scalars()
        .all()
    )
    lin = lineage.build(db, principal.tenant_id, m, e, p)
    return {
        "metric": {**serialize(m), "framework_requirements": _requirements_for(db, m)},
        "entity": {"code": e.code, "name": e.name, "kind": e.kind},
        "period": p.code,
        "card": card,
        "series": series,
        "value": serialize(mv),
        "calculation": calc,
        "evidence": evidence,
        "quality": quality,
        "governance": gov,
        "issues": serialize(issues),
        "targets": serialize(targets),
        "lineage": lin,
        "audit_history": serialize(history),
        "ai_analysis": {"available": True, "endpoint": "/api/v1/copilot/ask", "suggested_question": f"Why did {m.name} change in {p.code}?"},
    }


@router.get("/{code}/values")
def metric_values(code: str, principal: User, db: DB, period: str | None = None):
    m = get_metric(db, principal, code)
    stmt = select(MetricValue).where(MetricValue.metric_id == m.id)
    if period:
        stmt = stmt.join(ReportingPeriod, ReportingPeriod.id == MetricValue.period_id).where(ReportingPeriod.code == period)
    vals = db.execute(stmt).scalars().all()
    out = []
    for v in vals:
        ent, per = db.get(Entity, v.entity_id), db.get(ReportingPeriod, v.period_id)
        out.append({**serialize(v), "entity_code": ent.code, "period_code": per.code})
    return out


@router.post("/{code}/values", dependencies=[Depends(require("data.write"))])
def upsert_value(code: str, body: ValueIn, principal: User, db: DB):
    org = get_org(db, principal)
    m = get_metric(db, principal, code)
    e = get_entity(db, principal, org, body.entity_code)
    p = get_period(db, org, body.period_code)
    check_data_change(db, principal.tenant_id, period=p, object_type="metric_value", roles=principal.roles)
    from app.ai import guardrails

    findings = guardrails.validate_esg_value(
        {"data_type": m.data_type, "validation_rules": m.validation_rules}, body.value_numeric if body.value_numeric is not None else body.value_text
    )
    if any(f["severity"] == "HIGH" for f in findings):
        from app.core.errors import GuardrailError

        raise GuardrailError("Value rejected by input guardrail", details=findings)
    mv = db.execute(select(MetricValue).where(MetricValue.metric_id == m.id, MetricValue.entity_id == e.id, MetricValue.period_id == p.id)).scalars().first()
    old = serialize(mv) if mv else None
    if mv is None:
        mv = MetricValue(tenant_id=principal.tenant_id, metric_id=m.id, entity_id=e.id, period_id=p.id, created_by=principal.user_id, unit=m.unit)
        db.add(mv)
    mv.value_numeric, mv.value_text, mv.is_estimate, mv.confidence, mv.notes = body.value_numeric, body.value_text, body.is_estimate, body.confidence, body.notes
    mv.status, mv.source_type = "draft", "manual"
    db.flush()
    for ecode in body.evidence_codes:
        ev = db.execute(select(Evidence).where(Evidence.tenant_id == principal.tenant_id, Evidence.code == ecode)).scalars().first()
        if ev:
            db.add(EvidenceLink(evidence_id=ev.id, metric_id=m.id, metric_value_id=mv.id))
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="data.modify",
        object_type="metric_value",
        object_id=f"{m.code}/{e.code}/{p.code}",
        old_value=old,
        new_value={"value": body.value_numeric, "text": body.value_text},
        reason=body.reason,
    )
    metric_engine.recalculate_all(db, principal.tenant_id, org.id, p, user_id=principal.user_id)
    data_quality.assess(db, principal.tenant_id, m, e, p)
    run_metric_rules(db, principal.tenant_id, org.id, p)
    db.commit()
    return {**serialize(mv), "guardrail_findings": findings}


class StatusIn(BaseModel):
    entity_code: str | None = None
    period_code: str
    status: str
    comment: str | None = None


@router.post("/{code}/status")
def set_value_status(code: str, body: StatusIn, principal: User, db: DB):
    """Workflow: draft → validated (analyst) → approved (manager) → final (manager/approver)."""
    cap = {"validated": "metric.validate", "approved": "metric.approve", "final": "metric.approve", "draft": "data.write"}.get(body.status)
    if cap is None or not principal.has(cap):
        from app.core.errors import PermissionError_

        raise PermissionError_(f"Not permitted to set status {body.status}")
    org = get_org(db, principal)
    m = get_metric(db, principal, code)
    e = get_entity(db, principal, org, body.entity_code)
    p = get_period(db, org, body.period_code)
    mv = db.execute(select(MetricValue).where(MetricValue.metric_id == m.id, MetricValue.entity_id == e.id, MetricValue.period_id == p.id)).scalars().first()
    if mv is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("No value to transition")
    old = mv.status
    mv.status = body.status
    if body.status in ("approved", "final"):
        mv.approved_by = principal.user_id
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action=f"metric_value.{body.status}",
        object_type="metric_value",
        object_id=f"{m.code}/{e.code}/{p.code}",
        old_value={"status": old},
        new_value={"status": body.status},
        reason=body.comment,
    )
    run_metric_rules(db, principal.tenant_id, org.id, p)
    db.commit()
    return serialize(mv)


@router.post("/{code}/calculate", dependencies=[Depends(require("metric.write"))])
def calculate(code: str, principal: User, db: DB, entity: str | None = None, period: str | None = None, persist: bool = True):
    org = get_org(db, principal)
    m = get_metric(db, principal, code)
    e = get_entity(db, principal, org, entity)
    p = get_period(db, org, period)
    res = metric_engine.calculate(db, principal.tenant_id, m, e, p, user_id=principal.user_id, persist=persist)
    if persist:
        audit.record(
            db,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            action="calculation.run",
            object_type="metric_value",
            object_id=f"{m.code}/{e.code}/{p.code}",
            new_value={"result": res.value, "version": res.version, "status": res.status},
        )
        db.commit()
    return {**res.__dict__, "explanation": metric_engine.explain(res)}


@router.post("/{code}/formula", dependencies=[Depends(require("metric.approve"))])
def new_formula_version(code: str, body: FormulaIn, principal: User, db: DB):
    m = get_metric(db, principal, code)
    from app.engines.safe_expr import compile_formula, evaluate

    expr, mapping = compile_formula(body.formula)
    evaluate(expr, {v: 1.0 for v in mapping})  # syntax check
    for cv in db.execute(select(CalculationVersion).where(CalculationVersion.metric_id == m.id)).scalars().all():
        cv.is_current = False
    cv = CalculationVersion(
        tenant_id=principal.tenant_id, metric_id=m.id, version=body.version, formula=body.formula, description=body.description, is_current=True, approved_by=principal.user_id
    )
    db.add(cv)
    m.formula = body.formula
    m.version += 1
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="calculation.version",
        object_type="metric_definition",
        object_id=m.code,
        new_value={"version": body.version, "formula": body.formula},
    )
    db.commit()
    return serialize(cv)


@router.get("/{code}/lineage")
def metric_lineage(code: str, principal: User, db: DB, entity: str | None = None, period: str | None = None):
    org = get_org(db, principal)
    m = get_metric(db, principal, code)
    e = get_entity(db, principal, org, entity)
    p = get_period(db, org, period)
    return {"graph": lineage.build(db, principal.tenant_id, m, e, p), "chain": lineage.chain(db, principal.tenant_id, m, e, p)}


@router.get("/{code}/runs")
def calculation_runs(code: str, principal: User, db: DB, limit: int = 20):
    m = get_metric(db, principal, code)
    runs = db.execute(select(CalculationRun).where(CalculationRun.metric_id == m.id).order_by(CalculationRun.executed_at.desc()).limit(limit)).scalars().all()
    return [{**serialize(r), "entity_code": db.get(Entity, r.entity_id).code, "period_code": db.get(ReportingPeriod, r.period_id).code} for r in runs]


# ------------------------------------------------------------------ targets & recalculation
targets_router = APIRouter(prefix="/targets", tags=["targets"])


@targets_router.get("")
def list_targets(principal: User, db: DB, status: str | None = None):
    stmt = select(Target).where(Target.tenant_id == principal.tenant_id)
    if status:
        stmt = stmt.where(Target.status == status)
    out = []
    for t in db.execute(stmt).scalars().all():
        m, e = db.get(MetricDefinition, t.metric_id), db.get(Entity, t.entity_id)
        org = get_org(db, principal)
        p = get_period(db, org, None)
        cur, _ = metric_engine.get_value(db, principal.tenant_id, m.code, e, p)
        progress = None
        if t.target_value is not None and t.baseline_value not in (None, t.target_value) and cur is not None:
            progress = round((cur - t.baseline_value) / (t.target_value - t.baseline_value) * 100, 1)
        out.append(
            {
                **serialize(t),
                "metric_code": m.code,
                "metric_name": m.name,
                "unit": m.unit,
                "entity_code": e.code,
                "current_value": cur,
                "current_period": p.code,
                "progress_pct": progress,
            }
        )
    return out


@targets_router.post("", dependencies=[Depends(require("metric.write"))])
def create_target(body: TargetIn, principal: User, db: DB):
    org = get_org(db, principal)
    m = get_metric(db, principal, body.metric_code)
    e = get_entity(db, principal, org, body.entity_code)
    t = Target(tenant_id=principal.tenant_id, metric_id=m.id, entity_id=e.id, **body.model_dump(exclude={"metric_code", "entity_code"}))
    db.add(t)
    db.flush()
    audit.record(db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="target.create", object_type="target", object_id=t.id, new_value=body.model_dump())
    db.commit()
    return serialize(t)


calc_router = APIRouter(prefix="/calculations", tags=["calculations"])


@calc_router.post("/recalculate", dependencies=[Depends(require("metric.write"))])
def recalculate(principal: User, db: DB, period: str | None = None, org_id: int | None = None):
    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    results = metric_engine.recalculate_all(db, principal.tenant_id, org.id, p, user_id=principal.user_id)
    data_quality.assess_all(db, principal.tenant_id, org.id, p)
    gov = run_metric_rules(db, principal.tenant_id, org.id, p)
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="calculation.recalculate_all",
        object_type="reporting_period",
        object_id=p.code,
        new_value={"ok": len([r for r in results if r.status == "ok"]), "total": len(results)},
    )
    db.commit()
    return {
        "period": p.code,
        "calculated": len([r for r in results if r.status == "ok"]),
        "missing_inputs": len([r for r in results if r.status == "missing_inputs"]),
        "errors": [r.__dict__ for r in results if r.status == "error"],
        "governance": {k: v for k, v in gov.items() if k != "triggered"},
    }


@calc_router.get("/versions")
def calc_versions(principal: User, db: DB):
    rows = db.execute(select(CalculationVersion).where(CalculationVersion.tenant_id == principal.tenant_id)).scalars().all()
    return [{**serialize(cv), "metric_code": db.get(MetricDefinition, cv.metric_id).code, "metric_name": db.get(MetricDefinition, cv.metric_id).name} for cv in rows]
