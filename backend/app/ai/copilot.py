"""ESG AI Copilot: guardrail → Mixture-of-Experts route → specialised agents → aggregation → governance.

Answers are grounded in governed data via controlled tools and expose sources, metrics used, evidence,
confidence and the relevant framework. The copilot has no database access of its own.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai import guardrails
from app.ai.agents import registry as agent_registry
from app.ai.moe import EXPERTS, aggregate, classify
from app.core.security import Principal


def ask(db: Session, principal: Principal, question: str, *, period_code: str | None = None, entity_code: str | None = None, frameworks: list[str] | None = None) -> dict:
    guard = guardrails.check_input(question)
    if guard.blocked:
        return {
            "answer": "The request was rejected by the input guardrail.",
            "confidence": 0.0,
            "sources": [],
            "metrics_used": [],
            "guardrail": guard.as_dict(),
            "route": None,
            "status": "blocked",
        }
    route = classify(question)
    responses = []
    run_ids = []
    seen_agents: set[str] = set()
    for expert in route.experts:
        if expert.agent in seen_agents:
            continue  # never run the same agent twice for one question
        seen_agents.add(expert.agent)
        agent_cls = agent_registry.get(expert.agent)
        agent = agent_cls(db, principal)
        payload = {"question": guard.sanitized or question, "period_code": period_code or "", "entity_code": entity_code or "", "frameworks": frameworks}
        task = {
            "standards_mapping_agent": "gap_analysis",
            "calculation_agent": "explain",
            "evidence_agent": "review",
            "governance_agent": "check",
            "assurance_agent": "package",
            "materiality_agent": "assess",
        }.get(expert.agent, "answer")
        result = agent.run(task, payload, expert_hint=expert.system_hint)
        run_ids.append(result.run_id)
        answer = result.output.get("answer") or result.output.get("narrative") or ""
        responses.append(
            {
                "expert": expert.code,
                "agent": agent.spec.code,
                "answer": answer,
                "confidence": result.confidence,
                "sources": result.sources,
                "metrics_used": result.metrics_used,
                "evidence": sorted({e for m in result.output.get("metrics", []) if isinstance(m, dict) for e in m.get("evidence", [])})
                if isinstance(result.output.get("metrics"), list)
                else [],
                "status": result.status,
                "governance": result.governance,
                "evaluation": result.evaluation,
                "requires_human_review": result.requires_human_review,
                "extras": {k: v for k, v in result.output.items() if k in ("gaps", "recommendations", "findings", "package", "passages", "disclaimer")},
            }
        )
    merged = aggregate(responses)
    frameworks_mentioned = sorted(
        {s.strip("[]").split(" ")[0] for s in merged.get("sources", []) if any(s.strip("[]").startswith(f) for f in ("WEF", "GRI", "IFRS", "ESRS", "SASB", "UNGC", "SDG"))}
    )
    return {
        **merged,
        "route": route.as_dict(),
        "experts": [{"code": e.code, "name": e.name} for e in route.experts],
        "relevant_frameworks": frameworks_mentioned or (frameworks or ["WEF_SCM", "UNGC", "UN_SDG"]),
        "agent_runs": run_ids,
        "guardrail": guard.as_dict(),
        "status": "requires_review" if any(r["requires_human_review"] for r in responses) else "completed",
        "disclaimer": "Answers are generated from governed metrics and approved knowledge with citations; they are advisory and do not constitute a compliance opinion.",
    }


def experts() -> list[dict]:
    return [{"code": e.code, "name": e.name, "description": e.description, "agent": e.agent, "tools": e.tools} for e in EXPERTS.values()]
