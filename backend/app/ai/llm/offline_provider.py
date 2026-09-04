"""Offline / air-gapped provider.

Produces deterministic, formal narratives purely from the FACTS block the agent supplies (metric values with
citations). It never invents numbers: every figure in the output comes from the facts. This is also the
provider used by the test-suite so AI behaviour is reproducible.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from app.ai.llm.base import LLMResult

FACTS_RE = re.compile(r"FACTS:\s*(\{.*\}|\[.*\])\s*$", re.S)


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


class OfflineProvider:
    name = "offline"
    model = "deterministic-template-v1"

    def complete(
        self, *, system: str, messages: list[dict[str, Any]], json_schema: dict | None = None, max_tokens: int | None = None, effort: str | None = None, purpose: str = "general"
    ) -> LLMResult:
        started = time.perf_counter()
        user_text = ""
        for m in messages:
            if m.get("role") == "user":
                c = m.get("content")
                user_text = c if isinstance(c, str) else " ".join(b.get("text", "") for b in c if isinstance(b, dict))
        facts: Any = None
        match = FACTS_RE.search(user_text)
        if match:
            try:
                facts = json.loads(match.group(1))
            except json.JSONDecodeError:
                facts = None
        question = user_text.split("FACTS:")[0].strip()
        if json_schema is not None:
            parsed = self._structured(json_schema, facts, question)
            text = json.dumps(parsed)
        else:
            text = self._narrative(question, facts, purpose)
            parsed = None
        return LLMResult(text=text, provider=self.name, model=self.model, latency_ms=int((time.perf_counter() - started) * 1000), stop_reason="end_turn", parsed=parsed)

    # ------------------------------------------------------------------
    def _narrative(self, question: str, facts: Any, purpose: str) -> str:
        if not facts:
            return "Data unavailable. No governed metrics or approved knowledge were retrieved for this request; human review required before any statement can be made."
        items = facts.get("metrics", []) if isinstance(facts, dict) else facts
        sources = facts.get("sources", []) if isinstance(facts, dict) else []
        title = facts.get("title") if isinstance(facts, dict) else None
        lines: list[str] = []
        if title:
            lines.append(f"{title}.")
        for it in items:
            if not isinstance(it, dict):
                continue
            name = it.get("name") or it.get("code")
            val = it.get("value")
            unit = it.get("unit") or ""
            period = it.get("period") or ""
            entity = it.get("entity") or ""
            prev = it.get("previous")
            cite = it.get("citation") or (f"[{it.get('evidence')[0]}]" if it.get("evidence") else "")
            if val is None and not it.get("text"):
                lines.append(f"{name}: Data unavailable for {period or 'the reporting period'}{' (' + entity + ')' if entity else ''}; evidence required.")
                continue
            if it.get("text"):
                lines.append(f"{name}: {it['text']} {cite}".strip())
                continue
            sentence = f"{name} was {_fmt(val)} {unit}".strip()
            if entity:
                sentence += f" for {entity}"
            if period:
                sentence += f" in {period}"
            yoy = it.get("yoy_pct")
            if prev is not None and isinstance(prev, (int, float)) and isinstance(yoy, (int, float)):
                if yoy:
                    direction = "an increase" if yoy > 0 else "a decrease"
                    sentence += f", {direction} of {abs(yoy):.1f}% against the prior period ({_fmt(prev)} {unit})".rstrip()
                else:
                    sentence += f", unchanged from the prior period ({_fmt(prev)} {unit})".rstrip()
            lines.append((sentence + f" {cite}").strip() + ".")
        passages = facts.get("passages", []) if isinstance(facts, dict) and purpose != "draft_section" else []
        if passages:
            ctx = []
            for p in passages[:3]:
                if isinstance(p, dict) and p.get("text"):
                    ctx.append(f"{p.get('citation', '')} {str(p['text'])[:280].strip()}")
            if ctx:
                lines.append("Supporting context from approved knowledge: " + " … ".join(ctx) + ".")
        findings = facts.get("findings", []) if isinstance(facts, dict) else []
        if findings:
            rendered = []
            for f in findings[:8]:
                if isinstance(f, dict):
                    rendered.append("; ".join(f"{k}: {v}" for k, v in f.items() if v not in (None, "", [], {}) and k != "context")[:220])
                else:
                    rendered.append(str(f)[:220])
            lines.append("Findings: " + " | ".join(rendered) + ".")
        recs = facts.get("recommendations", []) if isinstance(facts, dict) else []
        if recs:
            lines.append("Recommended actions: " + " ".join(f"({i + 1}) {r}" for i, r in enumerate(recs[:6])))
        if isinstance(facts, dict) and facts.get("disclaimer"):
            lines.append(str(facts["disclaimer"]))
        if sources:
            lines.append("Sources: " + "; ".join(str(s) for s in sources[:6]) + ".")
        if purpose == "report_section":
            lines.append("All figures are drawn from governed metric values with linked evidence; no estimates have been introduced by the drafting process.")
        return " ".join(lines)

    def _structured(self, schema: dict, facts: Any, question: str) -> dict:
        props = schema.get("properties", {})
        out: dict[str, Any] = {}
        for key, spec in props.items():
            t = spec.get("type")
            if key in ("summary", "answer", "narrative", "explanation", "rationale"):
                out[key] = self._narrative(question, facts, "general")
            elif key == "confidence":
                out[key] = 0.9 if facts else 0.2
            elif t == "array":
                out[key] = []
            elif t == "boolean":
                out[key] = bool(facts)
            elif t in ("number", "integer"):
                out[key] = 0
            elif t == "object":
                out[key] = {}
            else:
                out[key] = ""
        if facts and isinstance(facts, dict):
            for key in ("recommendations", "findings", "gaps", "mappings", "classifications"):
                if key in props and key in facts:
                    out[key] = facts[key]
        return out
