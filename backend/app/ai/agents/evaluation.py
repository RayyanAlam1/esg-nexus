"""Evaluation Agent scoring: factuality, groundedness, relevance, citation correctness, numerical
consistency and hallucination rate. Deterministic so evaluation is reproducible and trackable over time."""

from __future__ import annotations

import re

from app.ai import guardrails
from app.ai.rag.index import tokenize

WEIGHTS = {"factuality": 0.25, "groundedness": 0.2, "relevance": 0.15, "citation_correctness": 0.15, "numerical_consistency": 0.25}
CITATION_RE = re.compile(r"\[([^\]]+)\]")


def _fact_texts(facts: dict) -> list[str]:
    out = []
    for m in facts.get("metrics", []) or []:
        if isinstance(m, dict):
            out.append(" ".join(str(v) for v in m.values() if isinstance(v, (str, int, float))))
    for s in facts.get("passages", []) or []:
        out.append(s.get("text", "") if isinstance(s, dict) else str(s))
    for f in facts.get("findings", []) or []:
        out.append(str(f))
    return out


def score_output(text: str, *, facts: dict, question: str = "", guard: guardrails.GuardrailResult | None = None) -> dict:
    guard = guard or guardrails.check_output(text, allowed_numbers=[], sources=facts.get("sources"), require_citations=False)
    n_sup, n_unsup = len(guard.supported_numbers), len(guard.unsupported_numbers)
    factuality = 100.0 if n_sup + n_unsup == 0 else n_sup / (n_sup + n_unsup) * 100
    numerical = factuality

    fact_tokens = [set(tokenize(t)) for t in _fact_texts(facts)]
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text or "") if len(s.split()) > 3]
    grounded = 0
    for s in sentences:
        st = set(tokenize(s))
        if not st:
            continue
        if any(len(st & ft) / len(st) >= 0.3 for ft in fact_tokens):
            grounded += 1
    groundedness = (grounded / len(sentences) * 100) if sentences else (100.0 if not text else 0.0)

    qt, at = set(tokenize(question)), set(tokenize(text or ""))
    relevance = (len(qt & at) / len(qt) * 100) if qt else 100.0
    relevance = max(relevance, 40.0) if facts.get("metrics") else relevance

    known = set()
    for m in facts.get("metrics", []) or []:
        if isinstance(m, dict) and m.get("citation"):
            known.add(m["citation"].strip("[]"))
    for s in facts.get("sources", []) or []:
        known.add(str(s).strip("[]"))
    cites = CITATION_RE.findall(text or "")
    if cites:
        ok = sum(1 for c in cites if c in known or any(c.split(" ")[0] == k.split(" ")[0] for k in known))
        citation = ok / len(cites) * 100
    else:
        citation = 100.0 if not (facts.get("metrics") or facts.get("sources")) else 50.0

    scores = {
        "factuality": round(factuality, 1),
        "groundedness": round(groundedness, 1),
        "relevance": round(min(relevance, 100), 1),
        "citation_correctness": round(citation, 1),
        "numerical_consistency": round(numerical, 1),
        "hallucination_rate": round(100 - factuality, 1),
    }
    overall = round(sum(scores[k] * w for k, w in WEIGHTS.items()), 1)
    findings = []
    if guard.unsupported_numbers:
        findings.append({"type": "unsupported_numbers", "detail": guard.unsupported_numbers[:10]})
    if groundedness < 60:
        findings.append({"type": "low_groundedness", "detail": f"{groundedness:.0f}% of sentences grounded in facts"})
    if citation < 100 and cites:
        findings.append({"type": "citation_mismatch", "detail": "some citations do not match provided sources"})
    return {"scores": scores, "overall": overall, "findings": findings, "passed": overall >= 70}
