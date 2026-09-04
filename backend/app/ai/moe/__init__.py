"""Mixture-of-Experts router.

Input → task classification → expert(s) → expert response → validation → aggregation → final response.
Routing is deterministic (keyword/intent scoring) with an optional LLM classifier for ambiguous inputs; the
system never fans out to every expert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Expert:
    code: str
    name: str
    description: str
    keywords: list[str]
    tools: list[str]
    system_hint: str
    agent: str  # default agent that executes this expert's tasks


EXPERTS: dict[str, Expert] = {
    e.code: e
    for e in [
        Expert(
            "esg",
            "ESG Expert",
            "General ESG performance, topics and KPIs",
            ["esg", "sustainability", "kpi", "performance", "overview", "material"],
            ["search_metrics", "get_metric", "get_metric_history", "search_knowledge_base"],
            "You are a senior ESG analyst. Answer only from governed metrics and cited knowledge.",
            "rag_research_agent",
        ),
        Expert(
            "climate",
            "Climate Expert",
            "Climate strategy, TCFD/IFRS S2, targets, transition and physical risk",
            ["climate", "tcfd", "paris", "net zero", "net-zero", "transition", "physical risk", "scenario", "ifrs s2"],
            ["get_metric", "get_framework_requirement", "get_framework_mapping", "search_knowledge_base"],
            "You are a climate disclosure expert (TCFD / IFRS S2). Distinguish reported facts from gaps.",
            "standards_mapping_agent",
        ),
        Expert(
            "ghg",
            "GHG Expert",
            "GHG inventory, scopes, intensities, energy",
            ["ghg", "emission", "scope 1", "scope 2", "scope 3", "co2", "tco2e", "carbon", "energy", "gj", "intensity", "renewable"],
            ["get_metric", "get_metric_history", "calculate_metric", "get_lineage", "get_evidence"],
            "You are a GHG accounting expert (GHG Protocol). Use governed values and the report's stated drivers; never compute numbers yourself.",
            "rag_research_agent",
        ),
        Expert(
            "calculation",
            "Calculation Expert",
            "Formula, inputs and versions behind a derived metric",
            ["calculat", "formula", "how is", "computed", "derived", "recalculate", "inputs", "methodology"],
            ["calculate_metric", "get_metric", "get_lineage"],
            "You explain approved formulas and their inputs; the deterministic engine computes.",
            "calculation_agent",
        ),
        Expert(
            "financial",
            "Financial Reporting Expert",
            "Economic value, tax, capex, wealth distribution",
            ["revenue", "ebitda", "profit", "pat", "tax", "capex", "dividend", "buyback", "wealth", "economic value", "financial", "eps", "pkr"],
            ["get_metric", "get_metric_history", "calculate_metric"],
            "You are a financial reporting expert. Use the wealth generated and distributed statement; state currency and period.",
            "rag_research_agent",
        ),
        Expert(
            "governance",
            "Governance Expert",
            "Board, ethics, anti-corruption, policies",
            ["board", "director", "ethics", "corruption", "bribery", "whistleblow", "speak out", "code of conduct", "committee", "independence", "policy"],
            ["get_metric", "search_knowledge_base", "get_framework_requirement"],
            "You are a corporate governance expert. Reference board composition and ethics metrics with citations.",
            "governance_agent",
        ),
        Expert(
            "risk",
            "Risk Expert",
            "Enterprise, climate and ESG risk, issues, readiness",
            ["risk", "issue", "critical", "blocking", "readiness", "ready to publish", "what is missing", "gap", "preventing"],
            ["get_open_issues", "get_report_readiness", "run_governance_check"],
            "You are an ESG risk and assurance expert. Prioritise by severity and give required actions.",
            "assurance_agent",
        ),
        Expert(
            "legal",
            "Legal / Compliance Expert",
            "Framework requirements, disclosure obligations, gap analysis",
            ["gri", "ifrs", "issb", "esrs", "sasb", "wef", "ungc", "sdg", "framework", "requirement", "disclosure", "incomplete", "coverage", "alignment", "standard"],
            ["get_framework_mapping", "get_framework_requirement", "search_knowledge_base"],
            "You are a sustainability-reporting standards expert. Report alignment and coverage, never certify compliance.",
            "standards_mapping_agent",
        ),
        Expert(
            "data_quality",
            "Data Quality Expert",
            "Completeness, accuracy, consistency, evidence, lineage",
            ["quality", "evidence", "lineage", "source", "traceab", "missing data", "anomal", "inconsisten", "validation", "dataset"],
            ["run_data_quality_check", "get_evidence", "get_lineage", "get_dataset", "get_open_issues"],
            "You are a data-quality expert. Explain scores and deductions and cite evidence.",
            "evidence_agent",
        ),
        Expert(
            "statistics",
            "Statistics Expert",
            "Trends, year-over-year change, comparisons, benchmarks",
            ["trend", "change", "increase", "decrease", "yoy", "year over year", "compare", "comparison", "why did", "declin", "grow", "benchmark", "history"],
            ["get_metric_history", "get_metric", "calculate_metric"],
            "You are a quantitative analyst. Use time series from get_metric_history and tool-computed YoY figures.",
            "rag_research_agent",
        ),
        Expert(
            "document",
            "Document Intelligence Expert",
            "Extraction and classification of ESG data from documents",
            ["extract", "document", "pdf", "upload", "classify", "map fields", "ingest", "parse", "table"],
            ["search_knowledge_base", "search_metrics"],
            "You are a document-intelligence expert. Map document fields to metric codes and flag uncertainty.",
            "esg_data_agent",
        ),
        Expert(
            "report_writing",
            "Report Writing Expert",
            "Formal narrative drafting for report sections",
            ["draft", "narrative", "write", "section", "report text", "summary", "executive summary", "generate"],
            ["get_metric", "get_metric_history", "get_evidence", "search_knowledge_base"],
            "You are a corporate sustainability report writer. Formal, objective, evidence-based, every figure cited.",
            "reporting_agent",
        ),
    ]
}


@dataclass
class Route:
    experts: list[Expert]
    scores: dict[str, float] = field(default_factory=dict)
    method: str = "keyword"

    @property
    def primary(self) -> Expert:
        return self.experts[0]

    def as_dict(self) -> dict:
        return {"primary": self.primary.code, "experts": [e.code for e in self.experts], "scores": self.scores, "method": self.method}


def classify(text: str, *, max_experts: int = 2) -> Route:
    t = (text or "").lower()
    scores: dict[str, float] = {}
    for code, ex in EXPERTS.items():
        s = 0.0
        for kw in ex.keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", t) or kw in t:
                s += 2.0 if len(kw) > 4 else 1.0
        if s:
            scores[code] = s
    if not scores:
        return Route([EXPERTS["esg"]], {"esg": 0.0}, "fallback")
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top = ranked[0][1]
    chosen = [EXPERTS[c] for c, s in ranked[:max_experts] if s >= max(1.0, top * 0.5)]
    return Route(chosen, dict(ranked), "keyword")


def aggregate(responses: list[dict]) -> dict:
    """Merge validated expert responses: highest-confidence answer first, union of sources/metrics."""
    if not responses:
        return {"answer": "Data unavailable.", "confidence": 0.0, "sources": [], "metrics_used": []}
    responses = sorted(responses, key=lambda r: -(r.get("confidence") or 0))
    primary = responses[0]
    sources, metrics = [], []
    for r in responses:
        for s in r.get("sources", []):
            if s not in sources:
                sources.append(s)
        for m in r.get("metrics_used", []):
            if m not in metrics:
                metrics.append(m)
    answer = primary.get("answer", "")
    for r in responses[1:]:
        extra = r.get("answer", "")
        if extra and extra not in answer:
            answer += "\n\n" + extra
    return {**primary, "answer": answer, "sources": sources, "metrics_used": metrics, "experts": [r.get("expert") for r in responses]}
