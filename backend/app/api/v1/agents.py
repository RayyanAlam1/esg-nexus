"""AI: agents, agent runs, controlled tools, knowledge base / RAG, copilot, evaluation centre."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from app.ai import copilot
from app.ai.agents import registry as agent_registry
from app.ai.rag.retriever import retrieve
from app.ai.tools import TOOLS
from app.api.deps import DB, Page, User, get_org, get_period, paginate, serialize
from app.core import audit
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.security import require
from app.models.ai import Agent, AgentRun, Evaluation, KnowledgeChunk, KnowledgeDocument, ModelRun

router = APIRouter(prefix="/agents", tags=["ai"])


class RunIn(BaseModel):
    task: str = "answer"
    payload: dict = {}


@router.get("")
def list_agents(principal: User, db: DB):
    rows = {a.code: a for a in db.execute(select(Agent)).scalars().all()}
    out = []
    for spec in agent_registry.specs():
        a = rows.get(spec.code)
        runs = db.execute(select(func.count(AgentRun.id)).where(AgentRun.tenant_id == principal.tenant_id, AgentRun.agent_code == spec.code)).scalar()
        avg_conf = db.execute(select(func.avg(AgentRun.confidence)).where(AgentRun.tenant_id == principal.tenant_id, AgentRun.agent_code == spec.code)).scalar()
        out.append(
            {
                "code": spec.code,
                "name": spec.name,
                "description": spec.description,
                "responsibilities": spec.responsibilities,
                "tools": spec.tools,
                "expert": spec.expert,
                "version": spec.version,
                "is_active": a.is_active if a else True,
                "runs": runs,
                "avg_confidence": round(avg_conf, 2) if avg_conf else None,
            }
        )
    return {
        "agents": out,
        "provider": get_settings().ai_provider,
        "model": get_settings().anthropic_model if get_settings().ai_provider == "anthropic" else "deterministic-template-v1",
    }


@router.get("/tools")
def tools(principal: User):
    return [{"name": t.name, "description": t.description, "schema": t.schema} for t in TOOLS.values()]


@router.get("/runs")
def runs(principal: User, db: DB, page: Page = Depends(), agent: str | None = None, status: str | None = None):
    stmt = select(AgentRun).where(AgentRun.tenant_id == principal.tenant_id)
    if agent:
        stmt = stmt.where(AgentRun.agent_code == agent)
    if status:
        stmt = stmt.where(AgentRun.status == status)
    return paginate(db, stmt.order_by(AgentRun.started_at.desc()), page, AgentRun)


@router.get("/runs/{run_id}")
def run_detail(run_id: int, principal: User, db: DB):
    r = db.get(AgentRun, run_id)
    if r is None or r.tenant_id != principal.tenant_id:
        raise NotFoundError("Run not found")
    ev = db.get(Evaluation, r.evaluation_id) if r.evaluation_id else None
    return {**serialize(r), "evaluation": serialize(ev), "model_runs": serialize(r.model_runs)}


@router.post("/{code}/run", dependencies=[Depends(require("ai.run"))])
def run_agent(code: str, body: RunIn, principal: User, db: DB):
    try:
        cls = agent_registry.get(code)
    except KeyError as exc:
        raise NotFoundError("Agent not found") from exc
    res = cls(db, principal).run(body.task, body.payload)
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="ai.generate",
        object_type="agent_run",
        object_id=res.run_id,
        new_value={"agent": code, "task": body.task, "status": res.status, "confidence": res.confidence},
    )
    db.commit()
    return res.as_dict()


# ------------------------------------------------------------------ copilot
copilot_router = APIRouter(prefix="/copilot", tags=["ai"])


class AskIn(BaseModel):
    question: str
    period_code: str | None = None
    entity_code: str | None = None
    frameworks: list[str] | None = None


@copilot_router.post("/ask", dependencies=[Depends(require("ai.run"))])
def ask(body: AskIn, principal: User, db: DB):
    result = copilot.ask(db, principal, body.question, period_code=body.period_code, entity_code=body.entity_code, frameworks=body.frameworks)
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="ai.copilot",
        object_type="copilot",
        new_value={"question": body.question[:300], "status": result.get("status"), "route": result.get("route")},
    )
    db.commit()
    return result


@copilot_router.get("/experts")
def experts(principal: User):
    return copilot.experts()


@copilot_router.get("/suggestions")
def suggestions(principal: User):
    return [
        "Why did our Scope 1 emissions increase in FY2023?",
        "Which WEF disclosures are incomplete?",
        "What evidence is missing for the KPIs?",
        "Show me the highest ESG risks.",
        "What changed from FY2022 to FY2023?",
        "Which entities have the highest hazardous waste?",
        "Generate a draft narrative for the climate section.",
        "What is preventing report publication?",
        "Explain how the contractor TRIR is calculated.",
        "Which IFRS S2 requirements have no data?",
    ]


# ------------------------------------------------------------------ knowledge base
knowledge_router = APIRouter(prefix="/knowledge", tags=["ai"])


class SearchIn(BaseModel):
    query: str
    limit: int = 8
    kind: str | None = None


@knowledge_router.get("/documents")
def documents(principal: User, db: DB):
    rows = db.execute(select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == principal.tenant_id).order_by(KnowledgeDocument.code)).scalars().all()
    out = []
    for d in rows:
        allowed = "*" in (d.permissions or {}).get("roles", ["*"]) or bool(set((d.permissions or {}).get("roles", [])) & set(principal.roles))
        out.append({**serialize(d), "chunks": db.execute(select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.document_id == d.id)).scalar(), "accessible": allowed})
    return out


@knowledge_router.post("/search")
def search(body: SearchIn, principal: User, db: DB):
    hits = retrieve(db, principal, body.query, limit=body.limit, kind=body.kind)
    return {"query": body.query, "hits": [h.as_dict() for h in hits], "index": "lexical-bm25", "permission_filtered": True}


# ------------------------------------------------------------------ evaluation centre
evaluations_router = APIRouter(prefix="/evaluations", tags=["ai"])


@evaluations_router.get("")
def list_evaluations(principal: User, db: DB, page: Page = Depends(), dimension: str | None = None, object_type: str | None = None):
    stmt = select(Evaluation).where(Evaluation.tenant_id == principal.tenant_id)
    if dimension:
        stmt = stmt.where(Evaluation.dimension == dimension)
    if object_type:
        stmt = stmt.where(Evaluation.object_type == object_type)
    return paginate(db, stmt.order_by(Evaluation.created_at.desc()), page, Evaluation)


@evaluations_router.get("/summary")
def summary(principal: User, db: DB, period: str | None = None, org_id: int | None = None):
    """Evaluation Centre: data quality, AI quality, ESG quality, report quality + readiness."""
    from app.engines import frameworks as fw_engine
    from app.engines.readiness import compute
    from app.models.ai import QualityScore
    from app.models.reporting import Report

    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    evals = db.execute(select(Evaluation).where(Evaluation.tenant_id == principal.tenant_id, Evaluation.dimension == "ai")).scalars().all()
    ai_scores: dict[str, list[float]] = {}
    for e in evals:
        for k, v in (e.scores or {}).items():
            ai_scores.setdefault(k, []).append(v)
    ai = {k: round(sum(v) / len(v), 1) for k, v in ai_scores.items()}
    ai_overall = round(sum(e.overall for e in evals) / len(evals), 1) if evals else None
    q = db.execute(
        select(func.avg(QualityScore.overall), func.avg(QualityScore.completeness), func.avg(QualityScore.accuracy), func.avg(QualityScore.consistency)).where(
            QualityScore.tenant_id == principal.tenant_id, QualityScore.period_id == p.id
        )
    ).first()
    fws = ["WEF_SCM", "UNGC", "UN_SDG"]
    cov = {fw: fw_engine.coverage(db, principal.tenant_id, org.id, p, fw) for fw in fws}
    rd = compute(db, principal.tenant_id, org.id, p, framework_codes=fws)
    reports = db.execute(select(Report).where(Report.tenant_id == principal.tenant_id, Report.period_id == p.id)).scalars().all()
    report_quality = None
    if reports:
        r = reports[-1]
        checks = (r.validation_result or {}).get("checks", [])
        report_quality = {
            "report_id": r.id,
            "status": r.status,
            "checks_passed": len([c for c in checks if c["passed"]]),
            "checks_total": len(checks),
            "structural_compliance": round(len([c for c in checks if c["passed"]]) / len(checks) * 100, 1) if checks else None,
        }
    total_metrics = db.execute(select(func.count()).select_from(select(QualityScore.metric_id).where(QualityScore.period_id == p.id).distinct().subquery())).scalar()
    model_runs = db.execute(
        select(func.count(ModelRun.id), func.sum(ModelRun.prompt_tokens), func.sum(ModelRun.completion_tokens), func.avg(ModelRun.latency_ms)).where(
            ModelRun.tenant_id == principal.tenant_id
        )
    ).first()
    guardrail_failures = db.execute(select(func.count(AgentRun.id)).where(AgentRun.tenant_id == principal.tenant_id, AgentRun.status == "blocked")).scalar()
    return {
        "period": p.code,
        "data_quality": {
            "overall": round(q[0], 1) if q and q[0] else None,
            "completeness": round(q[1], 1) if q and q[1] else None,
            "accuracy": round(q[2], 1) if q and q[2] else None,
            "consistency": round(q[3], 1) if q and q[3] else None,
        },
        "ai_quality": {"overall": ai_overall, "dimensions": ai, "evaluated_outputs": len(evals), "hallucination_rate": ai.get("hallucination_rate")},
        "esg_quality": {
            "framework_alignment": {fw: c["alignment_pct"] for fw, c in cov.items()},
            "disclosure_completeness": round(sum(c["completed"] for c in cov.values()) / max(1, sum(c["applicable"] for c in cov.values())) * 100, 1),
            "evidence_coverage": rd.components["evidence_coverage"],
            "metric_coverage": total_metrics,
        },
        "report_quality": report_quality,
        "readiness": {"overall": rd.overall, "components": rd.components},
        "overall_scores": {
            "ai_quality": ai_overall,
            "data_quality": round(q[0], 1) if q and q[0] else None,
            "evidence_coverage": rd.components["evidence_coverage"],
            "framework_alignment": rd.components["framework_alignment"],
            "report_readiness": rd.overall,
        },
        "observability": {
            "model_runs": model_runs[0] or 0,
            "prompt_tokens": int(model_runs[1] or 0),
            "completion_tokens": int(model_runs[2] or 0),
            "avg_model_latency_ms": round(model_runs[3] or 0),
            "guardrail_blocks": guardrail_failures,
        },
    }


@evaluations_router.get("/readiness")
def readiness(principal: User, db: DB, period: str | None = None, org_id: int | None = None, frameworks: str = "WEF_SCM,UNGC,UN_SDG"):
    from app.engines.readiness import compute

    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    rd = compute(db, principal.tenant_id, org.id, p, framework_codes=[f for f in frameworks.split(",") if f])
    return {
        "period": p.code,
        "overall": rd.overall,
        "components": rd.components,
        "open_issues": rd.open_issues,
        "blocking_issues": rd.blocking_issues,
        "explanation": rd.explanation,
        "ready_to_publish": rd.ready_to_publish,
    }


@evaluations_router.get("/trend")
def trend(principal: User, db: DB):
    rows = db.execute(select(Evaluation).where(Evaluation.tenant_id == principal.tenant_id, Evaluation.dimension == "ai").order_by(Evaluation.created_at)).scalars().all()
    return [{"at": e.created_at.isoformat(), "overall": e.overall, "object": f"{e.object_type}:{e.object_id}", "scores": e.scores} for e in rows[-100:]]
