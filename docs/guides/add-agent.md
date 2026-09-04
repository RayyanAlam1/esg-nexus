# Guide: Add an agent

An agent is a `BaseAgent` subclass with an `AgentSpec` and a deterministic `gather()` method. The base class provides the full pipeline (input guardrail → tools → provider → output guardrail → evaluation → governance → persistence), so a new agent only decides *which facts to collect* and *how to shape the output*.

Related: [../AGENTS.md](../AGENTS.md) · [../RAG.md](../RAG.md) · [../TESTING.md](../TESTING.md#4-ai-evaluation-suite-testsai_evals).

---

## 1. (Optional) add a controlled tool

Agents may only call tools listed in their spec, and every tool must exist in `backend/app/ai/tools/registry.py`. Add one when the agent needs data no existing tool returns:

```python
# backend/app/ai/tools/registry.py
from app.models.esg import Target

@tool("List targets for a metric with baseline, target value, year and status. Returns an empty list when no target is set — never invents targets.")
def get_targets(ctx: ToolContext, metric_code: str, entity_code: str = "") -> list[dict]:
    metric = ctx.metric(metric_code)                     # tenant-scoped, ValueError when unknown
    entity = ctx.entity(entity_code or None)             # enforces the principal's entity scope
    rows = ctx.db.execute(select(Target).where(Target.metric_id == metric.id, Target.entity_id == entity.id)).scalars().all()
    return [{"metric": metric.code, "entity": entity.code, "baseline": t.baseline_value, "target": t.target_value,
             "year": t.target_year, "direction": t.direction, "status": t.status,
             "citation": f"[target {metric.code} · {entity.code}]"} for t in rows]
```

Rules: first parameter is `ToolContext`; other parameters must be `str`, `int`, `float` or `bool` (the JSON schema is derived from the signature; defaults make them optional); return JSON-serialisable data; include a `citation` on any numeric fact so narratives can cite it; never compute ESG figures in a tool other than through the engines.

## 2. Implement the agent

Add the class to `backend/app/ai/agents/specialists.py` (or a new module):

```python
from app.ai.agents.base import AgentSpec, BaseAgent

class TargetTrackingAgent(BaseAgent):
    spec = AgentSpec(
        code="target_tracking_agent",
        name="Target Tracking Agent",
        description="Compares current performance with disclosed targets and flags metrics without targets.",
        responsibilities=["Compare actuals with targets", "Flag metrics without quantitative targets", "Explain progress with citations"],
        tools=["get_metric", "get_targets", "search_metrics"],
        expert="statistics",          # MoE expert profile whose system hint fits best
        version="1.0",
        narrative=True,               # False → no provider call; output is purely deterministic
        output_schema=None,           # optional JSON schema for structured outputs (Anthropic output_config.format)
    )

    def gather(self, task: str, payload: dict) -> dict:
        """Deterministic facts. Numbers only come from tools."""
        codes = payload.get("metric_codes") or [h["code"] for h in self.tool("search_metrics", query=payload.get("question", "target"), limit=5)]
        entity, period = payload.get("entity_code", ""), payload.get("period_code", "")
        metrics, findings, sources = [], [], []
        for code in codes[:6]:
            gm = self.tool("get_metric", metric_code=code, entity_code=entity, period_code=period)
            if not isinstance(gm, dict) or "error" in gm:
                continue
            metrics.append(gm)
            sources.append(gm["citation"])
            targets = self.tool("get_targets", metric_code=code, entity_code=entity)
            if not targets or all(t["target"] is None for t in targets):
                findings.append({"metric": code, "type": "target_not_set", "detail": "No quantitative target disclosed."})
            for t in targets:
                metrics.append({"code": f"{code}.target", "name": f"Target for {gm['name']}", "value": t["target"], "unit": gm["unit"],
                                "period": str(t["year"] or ""), "citation": t["citation"], "status": t["status"]})
                sources.append(t["citation"])
        return {"title": "Target tracking", "metrics": metrics, "sources": list(dict.fromkeys(sources)), "findings": findings}

    def prompt(self, task, payload, facts):
        return payload.get("question") or "Compare each metric with its target; state 'Data unavailable' or 'No target set' where applicable."

    def compose(self, task, payload, facts, llm_text):
        return {"answer": llm_text or "", "findings": facts.get("findings", []), "metrics": facts.get("metrics", [])}
```

Contract of `gather`'s return value: `metrics` (list of dicts with at least `code`, `name`, `value`, `citation`; optional `unit`, `period`, `entity`, `previous`, `evidence`, `text`, `data_unavailable`), `sources` (citation strings), optional `findings`, `passages` (`{citation, text, kind}`), `recommendations`, `title`. Every number the provider may mention must appear in these facts, otherwise the output guardrail blocks the narrative (`unsupported_numbers`) and GR-011 triggers.

## 3. Register it

```python
# backend/app/ai/agents/registry.py
from app.ai.agents.specialists import (..., TargetTrackingAgent)

AGENTS = {cls.spec.code: cls for cls in [ESGDataAgent, ..., AssuranceAgent, TargetTrackingAgent]}
```

`registry.register(cls)` also works at runtime for plug-ins. The seeder mirrors every spec into the `agents` table (`GET /agents`).

## 4. (Optional) route Copilot questions to it

Add an expert in `backend/app/ai/moe/__init__.py::EXPERTS` whose `agent` is the new code, or point an existing expert at it. Map the Copilot task name in `backend/app/ai/copilot.py` (the dict inside `ask()`), otherwise the agent receives task `"answer"`:

```python
Expert("targets", "Target Expert", "Targets, progress and gaps", ["target", "goal", "commitment", "progress", "on track"],
       ["get_metric", "get_targets"], "You are an ESG target-setting expert. Compare actuals with disclosed targets; never invent targets.", "target_tracking_agent"),
```

## 5. Run it

```bash
curl -X POST localhost:8000/api/v1/agents/target_tracking_agent/run -H "authorization: Bearer $T" \
  -H 'content-type: application/json' -d '{"task": "track", "payload": {"metric_codes": ["SOC.OHS.FATALITIES_EMP"], "period_code": "FY2023"}}'
```

Inspect the run with `GET /agents/runs/{run_id}`: `tools_used`, `guardrail_result.output.unsupported_numbers` (must be empty), `evaluation` (`overall ≥ 70`), `governance` (no `BLOCK`), `status` (`completed` or `requires_review`).

## 6. Test it

- Unit: call `TargetTrackingAgent(db, principal).gather("track", {...})` with the seeded database and assert on `metrics`/`findings`.
- Eval case (`tests/ai_evals`): a question routed to the agent, expected `metrics_used`, `answer_contains` a fact figure and `"No target"`/`"Data unavailable"` where appropriate, `status != "blocked"`.
- Governance: with the offline provider the narrative only contains fact numbers, so `hallucination_rate` must be 0.

## 7. Checklist

- [ ] `spec.tools` lists only registered tools; the agent never touches `self.db` for ESG numbers (reading catalogue metadata is acceptable, as the Materiality and Assurance agents do).
- [ ] Every numeric fact carries a `citation`.
- [ ] Missing data is surfaced as `data_unavailable`/findings, never filled in.
- [ ] Prompt text tells the model to write "Data unavailable" for gaps and to cite.
- [ ] Documented in [../AGENTS.md](../AGENTS.md#2-the-ten-agents-aiagentsspecialistspy).
