"""Base agent: the controlled execution pipeline every specialised agent follows.

    input guardrail → gather facts via controlled tools (deterministic) → provider (LLM or offline)
    → output guardrail → evaluation → governance rules (ai_output scope) → persist AgentRun/ModelRun

Facts-first design: numbers only ever come from tools; the model composes, classifies, explains.
"""

from __future__ import annotations

import contextlib
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai import guardrails
from app.ai.llm import LLMProvider, get_provider
from app.ai.tools import ToolContext, call_tool
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import Principal
from app.models.ai import AgentRun, Evaluation, ModelRun

log = get_logger("ai.agent")

BASE_SYSTEM = """You are {name}, a specialised agent inside ESG Nexus, an enterprise ESG system of record.
Rules you must never break:
1. Use ONLY the facts provided in the FACTS block. Never invent emissions, employee numbers, incidents, financial figures, targets, evidence or compliance status.
2. If a value is missing, write "Data unavailable" or "Evidence required" — do not estimate.
3. Cite every figure with the citation given in the facts, e.g. [ENV.GHG.SCOPE1 · ECORP · FY2023] or [KB-REPORT-2023 p.81-82].
4. Never claim a framework is "complied with"; describe alignment, coverage and gaps.
5. Write in formal, objective, corporate language suitable for an audited sustainability report.
{expert_hint}
Responsibilities: {responsibilities}"""


@dataclass
class AgentSpec:
    code: str
    name: str
    description: str
    responsibilities: list[str]
    tools: list[str]
    expert: str = "esg"
    version: str = "1.0"
    output_schema: dict | None = None
    narrative: bool = True  # whether the provider is asked to write prose


@dataclass
class AgentResult:
    agent: str
    task: str
    status: str
    output: dict
    confidence: float
    sources: list[str] = field(default_factory=list)
    metrics_used: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    guardrail: dict = field(default_factory=dict)
    evaluation: dict | None = None
    governance: list[dict] = field(default_factory=list)
    run_id: int | None = None
    provider: str | None = None
    latency_ms: int = 0
    requires_human_review: bool = False
    blocked: bool = False

    def as_dict(self) -> dict:
        return self.__dict__


class BaseAgent:
    spec: AgentSpec

    def __init__(self, db: Session, principal: Principal, provider: LLMProvider | None = None):
        self.db = db
        self.principal = principal
        self.provider = provider or get_provider()
        self.ctx = ToolContext(db, principal)
        self.tools_used: list[str] = []
        self.settings = get_settings()

    # -------- tool access (every call is recorded) ---------------------------------------------
    def tool(self, name: str, **kwargs) -> Any:
        if name not in self.spec.tools:
            raise PermissionError(f"Agent {self.spec.code} is not allowed to use tool {name}")
        self.tools_used.append(name)
        try:
            return call_tool(self.ctx, name, **kwargs)
        except (ValueError, PermissionError) as exc:
            return {"error": str(exc)}

    # -------- hooks implemented by specialised agents ------------------------------------------
    def gather(self, task: str, payload: dict) -> dict:
        """Return facts: {title, metrics: [...], sources: [...], findings: [...], ...}. Deterministic."""
        raise NotImplementedError

    def prompt(self, task: str, payload: dict, facts: dict) -> str:
        return payload.get("question") or payload.get("instruction") or f"Perform task '{task}'."

    def compose(self, task: str, payload: dict, facts: dict, llm_text: str | None) -> dict:
        """Build the structured output. Default: narrative + facts."""
        return {"answer": llm_text or "", "facts": facts}

    def uses_llm(self, task: str, payload: dict) -> bool:
        return self.spec.narrative

    def evaluation_query(self, task: str, payload: dict, facts: dict) -> str:
        """Text the relevance score compares the output against (default: the prompt)."""
        return self.prompt(task, payload, facts)

    # -------- pipeline --------------------------------------------------------------------------
    def run(self, task: str, payload: dict | None = None, *, persist: bool = True, evaluate: bool = True, expert_hint: str = "") -> AgentResult:
        from app.ai.agents.evaluation import score_output
        from app.services.governance_service import check_ai_output

        payload = payload or {}
        started = time.perf_counter()
        text_in = " ".join(str(v) for v in payload.values() if isinstance(v, str))
        in_guard = guardrails.check_input(text_in)
        model_runs: list[ModelRun] = []
        if in_guard.blocked:
            result = AgentResult(
                self.spec.code,
                task,
                "blocked",
                {"error": "Input rejected by guardrail", "findings": in_guard.findings},
                0.0,
                guardrail=in_guard.as_dict(),
                blocked=True,
                provider=self.provider.name,
            )
            return self._persist(result, payload, model_runs, started) if persist else result

        try:
            facts = self.gather(task, payload)
        except Exception as exc:  # tool failure is surfaced, never hidden
            log.warning("agent gather failed", agent=self.spec.code, error=str(exc))
            facts = {"error": str(exc), "metrics": [], "sources": []}

        llm_text: str | None = None
        parsed: Any = None
        provider_name = self.provider.name
        if self.uses_llm(task, payload):
            system = BASE_SYSTEM.format(name=self.spec.name, expert_hint=expert_hint, responsibilities="; ".join(self.spec.responsibilities))
            user = f"{self.prompt(task, payload, facts)}\n\nFACTS: {json.dumps(_jsonable(facts), ensure_ascii=False)}"
            res = self.provider.complete(system=system, messages=[{"role": "user", "content": user}], json_schema=self.spec.output_schema, purpose=task)
            model_runs.append(
                ModelRun(
                    tenant_id=self.principal.tenant_id,
                    provider=res.provider,
                    model=res.model,
                    purpose=f"{self.spec.code}:{task}",
                    prompt_tokens=res.prompt_tokens,
                    completion_tokens=res.completion_tokens,
                    cache_read_tokens=res.cache_read_tokens,
                    latency_ms=res.latency_ms,
                    status="ok" if res.ok else "error",
                    error=res.error or (json.dumps(res.refusal) if res.refusal else None),
                )
            )
            if res.ok:
                llm_text, parsed = res.text, res.parsed
            else:
                # degrade to the offline template rather than fail silently
                from app.ai.llm.offline_provider import OfflineProvider

                fallback = OfflineProvider().complete(system=system, messages=[{"role": "user", "content": user}], json_schema=self.spec.output_schema, purpose=task)
                llm_text, parsed, provider_name = fallback.text, fallback.parsed, f"{self.provider.name}→offline"
        output = self.compose(task, payload, facts, llm_text if parsed is None else json.dumps(parsed))
        if parsed is not None:
            output = {**output, **({"structured": parsed} if isinstance(parsed, dict) else {})}

        # output guardrail
        allowed = _numbers_in_facts(facts)
        narrative = output.get("answer") or output.get("narrative") or ""
        out_guard = guardrails.check_output(
            narrative,
            allowed_numbers=allowed,
            sources=facts.get("sources"),
            require_citations=bool(narrative) and self.spec.narrative,
            selected_frameworks=payload.get("frameworks"),
        )
        metrics_used = [m.get("code") for m in facts.get("metrics", []) if isinstance(m, dict) and m.get("code")]
        sources = list(
            dict.fromkeys(
                [m.get("citation") for m in facts.get("metrics", []) if isinstance(m, dict) and m.get("citation")] + [s for s in facts.get("sources", []) if isinstance(s, str)]
            )
        )
        confidence = _confidence(facts, out_guard)

        evaluation = None
        if evaluate and narrative:
            evaluation = score_output(narrative, facts=facts, question=self.evaluation_query(task, payload, facts), guard=out_guard)
            confidence = round(min(confidence, evaluation["overall"] / 100 + 0.05), 2)

        gov_ctx = {
            "agent": self.spec.code,
            "confidence": confidence,
            "has_sources": bool(sources),
            "unsupported_numbers": len(out_guard.unsupported_numbers),
            "missing_citations": out_guard.missing_citations,
            "injection_detected": in_guard.injection_detected,
            "guardrail_passed": out_guard.passed,
        }
        outcomes = check_ai_output(self.db, self.principal.tenant_id, gov_ctx)
        governance = [{"rule": o.rule_code, "severity": o.severity, "action": o.action, "message": o.message, "required_action": o.required_action} for o in outcomes]
        blocked = out_guard.blocked or any(o.blocks for o in outcomes)
        requires_review = blocked or any(o.action in ("REQUIRE_HUMAN_REVIEW", "REQUIRE_APPROVAL") for o in outcomes) or confidence < self.settings.ai_confidence_threshold
        status = "blocked" if blocked else ("requires_review" if requires_review else "completed")
        result = AgentResult(
            self.spec.code,
            task,
            status,
            output,
            confidence,
            sources,
            metrics_used,
            list(dict.fromkeys(self.tools_used)),
            {"input": in_guard.as_dict(), "output": out_guard.as_dict()},
            evaluation,
            governance,
            provider=provider_name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            requires_human_review=requires_review,
            blocked=blocked,
        )
        return self._persist(result, payload, model_runs, started) if persist else result

    def _persist(self, result: AgentResult, payload: dict, model_runs: list[ModelRun], started: float) -> AgentResult:
        run = AgentRun(
            tenant_id=self.principal.tenant_id,
            agent_code=self.spec.code,
            user_id=self.principal.user_id,
            task=result.task,
            input=_jsonable(payload),
            output=_jsonable(result.output),
            status=result.status,
            confidence=result.confidence,
            sources=result.sources,
            tools_used=result.tools_used,
            guardrail_result=result.guardrail,
            expert=self.spec.expert,
            provider=result.provider,
            finished_at=datetime.now(UTC),
            latency_ms=result.latency_ms,
        )
        self.db.add(run)
        self.db.flush()
        if result.evaluation:
            ev = Evaluation(
                tenant_id=self.principal.tenant_id,
                object_type="agent_run",
                object_id=str(run.id),
                evaluator="evaluation_agent",
                dimension="ai",
                scores=result.evaluation["scores"],
                overall=result.evaluation["overall"],
                findings=result.evaluation.get("findings"),
                passed=result.evaluation["overall"] >= 70,
            )
            self.db.add(ev)
            self.db.flush()
            run.evaluation_id = ev.id
        for mr in model_runs:
            mr.agent_run_id = run.id
            self.db.add(mr)
        self.db.flush()
        result.run_id = run.id
        return result


def _numbers_in_facts(facts: Any, acc: list[float] | None = None) -> list[float]:
    acc = acc if acc is not None else []
    if isinstance(facts, dict):
        for v in facts.values():
            _numbers_in_facts(v, acc)
    elif isinstance(facts, list):
        for v in facts:
            _numbers_in_facts(v, acc)
    elif isinstance(facts, bool):
        pass
    elif isinstance(facts, (int, float)):
        acc.append(float(facts))
    elif isinstance(facts, str):
        for m in guardrails.NUMBER_RE.finditer(facts):
            with contextlib.suppress(ValueError):
                acc.append(float(m.group(1).replace(",", "")))
    return acc


def _confidence(facts: dict, guard: guardrails.GuardrailResult) -> float:
    metrics = [m for m in facts.get("metrics", []) if isinstance(m, dict)]
    if not metrics and not facts.get("sources") and not facts.get("findings"):
        return 0.2
    with_values = [m for m in metrics if not m.get("data_unavailable")]
    base = 0.6 + 0.35 * (len(with_values) / len(metrics)) if metrics else 0.7
    if guard.unsupported_numbers:
        base -= 0.3
    if guard.missing_citations:
        base -= 0.1
    return round(max(0.0, min(0.98, base)), 2)


def _jsonable(obj: Any) -> Any:
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        return json.loads(json.dumps(obj, default=str))
