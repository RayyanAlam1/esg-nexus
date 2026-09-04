"""Controlled tools. Agents and the Copilot access enterprise data only through these functions.

Every tool receives a ToolContext (db session + principal) and enforces tenant scoping. New tools are added
with the @tool decorator — the registry exposes JSON schemas so an LLM can call them.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.engines import data_quality, lineage, metric_engine
from app.engines import frameworks as fw_engine
from app.engines.rules import metric_value_context
from app.models.data import Dataset, DatasetVersion
from app.models.esg import MetricDefinition, MetricValue, Target
from app.models.evidence import Evidence, EvidenceLink
from app.models.frameworks import Requirement
from app.models.organization import Entity, Organization, ReportingPeriod


@dataclass
class ToolContext:
    db: Session
    principal: Principal

    def org(self, code: str | None = None) -> Organization:
        stmt = select(Organization).where(Organization.tenant_id == self.principal.tenant_id)
        if code:
            stmt = stmt.where(Organization.code == code)
        org = self.db.execute(stmt).scalars().first()
        if org is None:
            raise ValueError("Organization not found")
        return org

    def entity(self, code: str | None) -> Entity:
        if code:
            e = self.db.execute(select(Entity).where(Entity.tenant_id == self.principal.tenant_id, Entity.code == code)).scalars().first()
        else:
            e = self.db.execute(select(Entity).where(Entity.tenant_id == self.principal.tenant_id, Entity.kind == "group")).scalars().first()
        if e is None:
            raise ValueError(f"Entity not found: {code}")
        if self.principal.entity_ids and e.id not in self.principal.entity_ids:
            raise PermissionError(f"Not authorised for entity {code}")
        return e

    def period(self, code: str | None) -> ReportingPeriod:
        org = self.org()
        stmt = select(ReportingPeriod).where(ReportingPeriod.organization_id == org.id)
        if code:
            p = self.db.execute(stmt.where(ReportingPeriod.code == code)).scalars().first()
        else:
            # default = latest period that actually has metric values (not an empty future period)
            from sqlalchemy import func

            periods = self.db.execute(stmt.order_by(ReportingPeriod.end_date.desc())).scalars().all()
            counts = {x.id: (self.db.execute(select(func.count(MetricValue.id)).where(MetricValue.period_id == x.id)).scalar() or 0) for x in periods}
            p = max(periods, key=lambda x: (counts[x.id], x.end_date)) if periods else None
        if p is None:
            raise ValueError(f"Reporting period not found: {code}")
        return p

    def metric(self, code: str) -> MetricDefinition:
        m = self.db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == self.principal.tenant_id, MetricDefinition.code == code)).scalars().first()
        if m is None:
            raise ValueError(f"Metric not found: {code}")
        return m


@dataclass
class ToolSpec:
    name: str
    description: str
    fn: Callable[..., Any]
    schema: dict

    def call(self, ctx: ToolContext, **kwargs) -> Any:
        return self.fn(ctx, **kwargs)


TOOLS: dict[str, ToolSpec] = {}


def tool(description: str):
    def deco(fn: Callable[..., Any]):
        sig = inspect.signature(fn)
        props, required = {}, []
        for pname, param in list(sig.parameters.items())[1:]:
            ann = param.annotation
            jtype = "string"
            if ann in (int, "int"):
                jtype = "integer"
            elif ann in (float, "float"):
                jtype = "number"
            elif ann in (bool, "bool"):
                jtype = "boolean"
            props[pname] = {"type": jtype}
            if param.default is inspect._empty:
                required.append(pname)
        schema = {"type": "object", "properties": props, "required": required, "additionalProperties": False}
        TOOLS[fn.__name__] = ToolSpec(fn.__name__, description, fn, schema)
        return fn

    return deco


def anthropic_tool_definitions(names: list[str] | None = None) -> list[dict]:
    return [{"name": t.name, "description": t.description, "input_schema": t.schema, "strict": True} for t in TOOLS.values() if names is None or t.name in names]


def _value_payload(db: Session, metric: MetricDefinition, entity: Entity, period: ReportingPeriod) -> dict:
    mv = db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == period.id)).scalars().first()
    value, consolidated = None, False
    if mv is not None and (mv.value_numeric is not None or mv.value_text):
        value = mv.value_numeric if mv.value_numeric is not None else mv.value_text
    else:
        v, _ = metric_engine.get_value(db, metric.tenant_id, metric.code, entity, period)
        value, consolidated = v, v is not None
    from app.engines.evidence_resolution import evidence_codes as _ev_codes

    evidence_codes: list[str] = _ev_codes(db, metric, entity, period, mv) if value is not None else []
    return {
        "code": metric.code,
        "name": metric.name,
        "unit": metric.unit,
        "pillar": metric.pillar,
        "topic": metric.topic_code,
        "kind": metric.kind,
        "entity": entity.code,
        "period": period.code,
        "value": value,
        "status": mv.status if mv else ("consolidated" if consolidated else "unavailable"),
        "source_type": mv.source_type if mv else ("consolidated" if consolidated else None),
        "is_estimate": bool(mv.is_estimate) if mv else False,
        "quality_score": mv.quality_score if mv else None,
        "evidence": sorted(set(evidence_codes)),
        "citation": f"[{metric.code} · {entity.code} · {period.code}]",
        "data_unavailable": value is None,
    }


# ---------------------------------------------------------------------------------------------- tools
@tool("Get a governed metric value with its evidence for an entity and reporting period. Returns 'Data unavailable' when no value exists — never guesses.")
def get_metric(ctx: ToolContext, metric_code: str, entity_code: str = "", period_code: str = "") -> dict:
    metric = ctx.metric(metric_code)
    entity = ctx.entity(entity_code or None)
    period = ctx.period(period_code or None)
    payload = _value_payload(ctx.db, metric, entity, period)
    prev = metric_engine.previous_period(ctx.db, period)
    if prev is not None:
        pv = _value_payload(ctx.db, metric, entity, prev)
        payload["previous"] = pv["value"] if isinstance(pv["value"], (int, float)) else None
        payload["previous_period"] = prev.code
        cur = payload["value"]
        if isinstance(cur, (int, float)) and payload["previous"] not in (None, 0):
            payload["yoy_pct"] = round((cur - payload["previous"]) / abs(payload["previous"]) * 100, 1)  # deterministic, tool-computed
    return payload


@tool("Get the time series of a metric for an entity across all reporting periods.")
def get_metric_history(ctx: ToolContext, metric_code: str, entity_code: str = "") -> dict:
    metric = ctx.metric(metric_code)
    entity = ctx.entity(entity_code or None)
    org = ctx.org()
    periods = ctx.db.execute(select(ReportingPeriod).where(ReportingPeriod.organization_id == org.id).order_by(ReportingPeriod.start_date)).scalars().all()
    series = [_value_payload(ctx.db, metric, entity, p) for p in periods]
    targets = ctx.db.execute(select(Target).where(Target.metric_id == metric.id, Target.entity_id == entity.id)).scalars().all()
    return {
        "code": metric.code,
        "name": metric.name,
        "unit": metric.unit,
        "entity": entity.code,
        "series": [{"period": s["period"], "value": s["value"], "evidence": s["evidence"], "status": s["status"]} for s in series],
        "targets": [{"target_value": t.target_value, "target_year": t.target_year, "direction": t.direction, "status": t.status, "description": t.description} for t in targets],
    }


@tool("Search the metric library by keyword (name, code, topic). Returns matching metric codes so a value can be requested with get_metric.")
def search_metrics(ctx: ToolContext, query: str, limit: int = 10) -> list[dict]:
    from app.ai.rag.index import tokenize

    words = [w for w in tokenize(query) if len(w) > 2]
    metrics = ctx.db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == ctx.principal.tenant_id, MetricDefinition.is_active == True)).scalars().all()  # noqa: E712
    scored = []
    for m in metrics:
        name, code = m.name.lower(), m.code.lower()
        hay = f"{code} {m.topic_code} {m.subtopic_code or ''} {m.description or ''}".lower()
        score = 0.0
        for w in words:
            if w in name:
                score += 3
            elif w in code:
                score += 2
            elif w in hay:
                score += 1
        if score:
            scored.append((score + (1.5 if m.is_kpi else 0) - (1 if m.kind == "narrative" else 0), m))
    scored.sort(key=lambda x: -x[0])
    return [{"code": m.code, "name": m.name, "unit": m.unit, "pillar": m.pillar, "topic": m.topic_code, "is_kpi": m.is_kpi, "kind": m.kind} for _, m in scored[:limit]]


@tool("Get a dataset and its latest version metadata (source, file hash, validation result).")
def get_dataset(ctx: ToolContext, dataset_code: str) -> dict:
    ds = ctx.db.execute(select(Dataset).where(Dataset.tenant_id == ctx.principal.tenant_id, Dataset.code == dataset_code)).scalars().first()
    if ds is None:
        raise ValueError("Dataset not found")
    dv = ctx.db.execute(select(DatasetVersion).where(DatasetVersion.dataset_id == ds.id).order_by(DatasetVersion.version.desc())).scalars().first()
    return {
        "code": ds.code,
        "name": ds.name,
        "pillar": ds.pillar,
        "source": ds.source.name,
        "source_kind": ds.source.kind,
        "latest_version": dv.version if dv else None,
        "file_name": dv.file_name if dv else None,
        "file_hash": dv.file_hash if dv else None,
        "status": dv.status if dv else None,
        "validation_result": dv.validation_result if dv else None,
        "row_count": dv.row_count if dv else 0,
    }


@tool("Get evidence items linked to a metric (optionally for one entity/period) with page references and verification status.")
def get_evidence(ctx: ToolContext, metric_code: str, entity_code: str = "", period_code: str = "") -> list[dict]:
    metric = ctx.metric(metric_code)
    stmt = select(EvidenceLink).where(EvidenceLink.metric_id == metric.id)
    if entity_code or period_code:
        entity = ctx.entity(entity_code or None)
        period = ctx.period(period_code or None)
        mv = ctx.db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == period.id)).scalars().first()
        stmt = stmt.where((EvidenceLink.metric_value_id == (mv.id if mv else -1)) | (EvidenceLink.metric_value_id.is_(None)))
    out = []
    for link in ctx.db.execute(stmt).scalars().all():
        ev = ctx.db.get(Evidence, link.evidence_id)
        if ev is None:
            continue
        out.append(
            {
                "code": ev.code,
                "title": ev.title,
                "kind": ev.kind,
                "document": ev.document_ref,
                "printed_page": ev.printed_page,
                "pdf_page": ev.page_from,
                "verification_status": ev.verification_status,
                "confidence": ev.confidence,
                "excerpt": (ev.excerpt or "")[:400],
                "relation": link.relation,
            }
        )
    uniq = {o["code"]: o for o in out}
    return list(uniq.values())


@tool("Get a framework requirement definition and its current fulfilment status for the organisation and period.")
def get_framework_requirement(ctx: ToolContext, requirement_code: str, period_code: str = "") -> dict:
    req = ctx.db.execute(select(Requirement).where(Requirement.code == requirement_code)).scalars().first()
    if req is None:
        raise ValueError("Requirement not found")
    org = ctx.org()
    period = ctx.period(period_code or None)
    status = fw_engine.requirement_status(ctx.db, ctx.principal.tenant_id, org.id, period, req)
    status["framework"] = req.framework_version.framework.code
    return status


@tool(
    "Get the framework coverage summary (alignment %, completed / partial / missing requirements, gaps) for a framework code such as WEF_SCM, GRI, IFRS_S, ESRS, UNGC, UN_SDG, SASB_CHEM."
)
def get_framework_mapping(ctx: ToolContext, framework_code: str, period_code: str = "") -> dict:
    org = ctx.org()
    period = ctx.period(period_code or None)
    cov = fw_engine.coverage(ctx.db, ctx.principal.tenant_id, org.id, period, framework_code)
    cov["requirements"] = [{k: v for k, v in r.items() if k != "guidance"} for r in cov["requirements"]]
    return cov


@tool("Run the deterministic calculation engine for a derived metric and return the formula, inputs and result. The AI never computes numbers itself.")
def calculate_metric(ctx: ToolContext, metric_code: str, entity_code: str = "", period_code: str = "") -> dict:
    metric = ctx.metric(metric_code)
    entity = ctx.entity(entity_code or None)
    period = ctx.period(period_code or None)
    res = metric_engine.calculate(ctx.db, ctx.principal.tenant_id, metric, entity, period, user_id=ctx.principal.user_id, persist=False)
    return {
        "metric": res.metric_code,
        "entity": res.entity_code,
        "period": res.period_code,
        "status": res.status,
        "value": res.value,
        "formula": res.formula,
        "version": res.version,
        "inputs": res.inputs,
        "message": res.message,
        "explanation": metric_engine.explain(res),
    }


@tool("Run the data-quality assessment for a metric value and return the seven dimension scores with explanations.")
def run_data_quality_check(ctx: ToolContext, metric_code: str, entity_code: str = "", period_code: str = "") -> dict:
    metric = ctx.metric(metric_code)
    entity = ctx.entity(entity_code or None)
    period = ctx.period(period_code or None)
    res = data_quality.assess(ctx.db, ctx.principal.tenant_id, metric, entity, period, persist=False)
    return {"metric": res.metric_code, "entity": res.entity_code, "period": res.period_code, "scores": res.scores, "overall": res.overall, "explanation": res.explanation}


@tool("Evaluate governance rules for a metric value and return triggered rules, severities and required actions.")
def run_governance_check(ctx: ToolContext, metric_code: str, entity_code: str = "", period_code: str = "") -> dict:
    from app.engines import rules as rules_engine

    metric = ctx.metric(metric_code)
    entity = ctx.entity(entity_code or None)
    period = ctx.period(period_code or None)
    mv = ctx.db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == period.id)).scalars().first()
    context = metric_value_context(ctx.db, metric, entity, period, mv)
    outcomes = rules_engine.evaluate_rules(rules_engine.active_rules(ctx.db, ctx.principal.tenant_id, "metric_value"), context)
    return {
        "metric": metric.code,
        "entity": entity.code,
        "period": period.code,
        "triggered": [
            {"rule": o.rule_code, "severity": o.severity, "action": o.action, "message": o.message, "required_action": o.required_action} for o in outcomes if o.triggered
        ],
        "evaluated": len(outcomes),
    }


@tool("Get the lineage graph for a reported value: metric → calculation → inputs → dataset → source → evidence.")
def get_lineage(ctx: ToolContext, metric_code: str, entity_code: str = "", period_code: str = "") -> dict:
    metric = ctx.metric(metric_code)
    entity = ctx.entity(entity_code or None)
    period = ctx.period(period_code or None)
    return lineage.build(ctx.db, ctx.principal.tenant_id, metric, entity, period)


@tool("Search the approved ESG knowledge base (report pages, framework requirements, metric definitions, policies, methodologies). Permission-filtered; returns cited passages.")
def search_knowledge_base(ctx: ToolContext, query: str, limit: int = 6, kind: str = "") -> list[dict]:
    from app.ai.rag.retriever import retrieve

    hits = retrieve(ctx.db, ctx.principal, query, limit=limit, kind=kind or None)
    return [h.as_dict() for h in hits]


@tool("List open issues (criticality engine) optionally filtered by severity or metric code.")
def get_open_issues(ctx: ToolContext, severity: str = "", metric_code: str = "", limit: int = 20) -> list[dict]:
    from app.models.governance import Issue

    stmt = select(Issue).where(Issue.tenant_id == ctx.principal.tenant_id, Issue.status.in_(["open", "acknowledged"]))
    if severity:
        stmt = stmt.where(Issue.severity == severity.upper())
    if metric_code:
        stmt = stmt.where(Issue.metric_code == metric_code)
    issues = ctx.db.execute(stmt.order_by(Issue.severity.desc()).limit(limit)).scalars().all()
    return [
        {
            "code": i.code,
            "severity": i.severity,
            "category": i.category,
            "title": i.title,
            "metric": i.metric_code,
            "entity": i.entity_code,
            "period": i.period_code,
            "required_action": i.required_action,
            "blocks_report": i.blocks_report,
        }
        for i in issues
    ]


@tool("Get report readiness (overall score, components, blocking issues) for the organisation and period.")
def get_report_readiness(ctx: ToolContext, period_code: str = "", framework_codes: str = "WEF_SCM,UNGC,UN_SDG") -> dict:
    from app.engines.readiness import compute

    org = ctx.org()
    period = ctx.period(period_code or None)
    r = compute(ctx.db, ctx.principal.tenant_id, org.id, period, framework_codes=[c.strip() for c in framework_codes.split(",") if c.strip()])
    return {
        "overall": r.overall,
        "components": r.components,
        "open_issues": r.open_issues,
        "blocking_issues": r.blocking_issues,
        "explanation": r.explanation,
        "ready_to_publish": r.ready_to_publish,
    }


@tool("List entities (subsidiaries, facilities) with their consolidation settings.")
def list_entities(ctx: ToolContext) -> list[dict]:
    org = ctx.org()
    ents = ctx.db.execute(select(Entity).where(Entity.organization_id == org.id).order_by(Entity.code)).scalars().all()
    return [
        {
            "code": e.code,
            "name": e.name,
            "kind": e.kind,
            "parent_id": e.parent_id,
            "ownership_pct": e.ownership_pct,
            "consolidation": e.consolidation_method,
            "in_boundary": e.in_reporting_boundary,
            "attributes": e.attributes or {},
        }
        for e in ents
    ]


def call_tool(ctx: ToolContext, name: str, **kwargs) -> Any:
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    return TOOLS[name].call(ctx, **kwargs)
