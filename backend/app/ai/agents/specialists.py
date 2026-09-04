"""The ten specialised agents. Each declares its tools and implements deterministic `gather`.

To add a new agent: subclass BaseAgent, set `spec`, implement `gather` (and optionally `compose`), and
register it in `app.ai.agents.registry` — see docs/guides/add-agent.md.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from app.ai.agents.base import AgentSpec, BaseAgent
from app.ai.rag.index import tokenize
from app.models.esg import MetricDefinition
from app.models.materiality import MaterialityAssessment, MaterialityTopic
from app.models.organization import Entity

CODE_RE = re.compile(r"\b(ENV|SOC|GOV|ECO)\.[A-Z0-9_]+\.[A-Z0-9_]+\b")
ENTITY_RE = re.compile(r"\b(ECORP-HQ|ECORP|EFERT|EPCL|EEL|EPQL|EPTL|SECMC|EVTL_EETL|EVTL|EETL|EEAP|ENFRA|FCEPL|EEFZE|EF|TF)\b")
PERIOD_RE = re.compile(r"\b(FY)?(20[12]\d)\b")


def _periods_in(text: str) -> list[str]:
    return list(dict.fromkeys(f"FY{m.group(2)}" for m in PERIOD_RE.finditer(text or "")))


def _entity_in(text: str) -> str:
    m = ENTITY_RE.search(text or "")
    return m.group(1) if m else ""


class ESGDataAgent(BaseAgent):
    spec = AgentSpec(
        "esg_data_agent",
        "ESG Data Agent",
        "Understands incoming datasets, classifies fields, detects missing/inconsistent values and proposes metric mappings.",
        ["Understand incoming ESG datasets", "Identify fields", "Classify data", "Detect missing fields", "Detect inconsistent values", "Suggest mappings"],
        ["search_metrics", "search_knowledge_base", "list_entities"],
        expert="document",
        narrative=False,
    )

    def gather(self, task: str, payload: dict) -> dict:
        columns: list[str] = payload.get("columns") or []
        rows: list[dict] = payload.get("rows") or []
        mappings, findings = [], []
        for col in columns:
            hits = self.tool("search_metrics", query=col.replace("_", " "), limit=3)
            best = hits[0] if isinstance(hits, list) and hits else None
            conf = 0.0
            if best:
                ct, mt = set(tokenize(col.replace("_", " "))), set(tokenize(best["name"]))
                conf = round(len(ct & mt) / (len(ct) or 1), 2)
            mappings.append(
                {
                    "column": col,
                    "metric_code": best["code"] if best else None,
                    "metric_name": best["name"] if best else None,
                    "confidence": conf,
                    "alternatives": [h["code"] for h in hits[1:]] if isinstance(hits, list) else [],
                }
            )
        required = {"metric_code", "entity_code", "period_code", "value"}
        present = set(columns)
        if not required & present and not any(m["metric_code"] for m in mappings):
            findings.append({"type": "missing_fields", "severity": "HIGH", "detail": "No metric/value columns recognised"})
        for f in ("entity_code", "period_code"):
            if f not in present:
                findings.append({"type": "missing_field", "severity": "MEDIUM", "detail": f"Column '{f}' not found — will default to group entity / current period"})
        for i, r in enumerate(rows[:500]):
            for col, val in r.items():
                if val in (None, ""):
                    findings.append({"type": "missing_value", "severity": "LOW", "row": i, "column": col})
                elif (
                    isinstance(val, str)
                    and re.fullmatch(r"-?[\d,]+(\.\d+)?%?", val.strip()) is None
                    and col in {m["column"] for m in mappings if m["metric_code"]}
                    and col not in ("metric_code", "entity_code", "period_code", "unit", "notes")
                ):
                    findings.append({"type": "non_numeric", "severity": "MEDIUM", "row": i, "column": col, "value": val})
        return {"title": "Dataset classification", "mappings": mappings, "findings": findings[:200], "columns": columns, "row_count": len(rows), "metrics": [], "sources": []}

    def compose(self, task, payload, facts, llm_text):
        return {
            "mappings": facts["mappings"],
            "findings": facts["findings"],
            "summary": f"{len([m for m in facts['mappings'] if m['metric_code']])} of {len(facts['columns'])} columns mapped; {len(facts['findings'])} finding(s).",
        }


class CalculationAgent(BaseAgent):
    spec = AgentSpec(
        "calculation_agent",
        "ESG Calculation Agent",
        "Identifies required calculations, selects approved formulas and explains them. Numbers are computed only by the deterministic engine.",
        ["Identify required calculations", "Select approved formulas", "Explain calculations", "Never invent authoritative formulas"],
        ["calculate_metric", "get_metric", "get_metric_history", "get_lineage", "search_metrics"],
        expert="ghg",
    )

    def gather(self, task: str, payload: dict) -> dict:
        q = payload.get("question", "")
        codes = payload.get("metric_codes") or CODE_RE.findall(q)
        if not codes:
            hits = self.tool("search_metrics", query=q, limit=4)
            codes = [h["code"] for h in hits if h.get("kind") in ("derived", "ratio", "intensity", "percentage", "yoy")] or [h["code"] for h in hits[:2]]
        entity = payload.get("entity_code") or _entity_in(q)
        periods = payload.get("periods") or _periods_in(q) or [payload.get("period_code") or ""]
        metrics, findings, sources = [], [], []
        for code in codes[:4]:
            for period in periods[:3]:
                calc = self.tool("calculate_metric", metric_code=code, entity_code=entity, period_code=period)
                if "error" in calc:
                    findings.append({"metric": code, "error": calc["error"]})
                    continue
                gm = self.tool("get_metric", metric_code=code, entity_code=entity, period_code=period)
                metrics.append(
                    {
                        **gm,
                        "calculated": calc.get("value"),
                        "formula": calc.get("formula"),
                        "formula_version": calc.get("version"),
                        "inputs": calc.get("inputs"),
                        "calc_status": calc.get("status"),
                        "explanation": calc.get("explanation"),
                    }
                )
                sources.append(gm.get("citation"))
                for icode, inp in (calc.get("inputs") or {}).items():
                    if inp.get("value") is not None:
                        base = icode.split("@")[0]
                        metrics.append(
                            {
                                "code": base,
                                "name": f"Input {icode}",
                                "value": inp.get("value"),
                                "entity": inp.get("entity"),
                                "period": inp.get("period"),
                                "citation": f"[{base} · {inp.get('entity')} · {inp.get('period')}]",
                            }
                        )
        return {"title": "Calculation explanation", "metrics": metrics, "sources": list(dict.fromkeys(sources)), "findings": findings}

    def prompt(self, task, payload, facts):
        return (
            payload.get("question") or "Explain the calculation of the requested metrics, listing formula, version, inputs and result. State 'Data unavailable' for missing inputs."
        )


class StandardsMappingAgent(BaseAgent):
    spec = AgentSpec(
        "standards_mapping_agent",
        "Standards Mapping Agent",
        "Maps metrics to frameworks, identifies applicable requirements and gaps, explains mapping decisions.",
        ["Map metrics to frameworks", "Identify disclosure requirements", "Identify gaps", "Identify applicable standards", "Explain mapping decisions"],
        ["get_framework_mapping", "get_framework_requirement", "search_knowledge_base", "search_metrics"],
        expert="legal",
    )

    def gather(self, task: str, payload: dict) -> dict:
        q = payload.get("question", "")
        fw = payload.get("framework_code") or self._framework_in(q) or "WEF_SCM"
        period = payload.get("period_code") or (_periods_in(q) or [""])[0]
        cov = self.tool("get_framework_mapping", framework_code=fw, period_code=period)
        if "error" in cov:
            return {"title": f"Framework gap analysis — {fw}", "metrics": [], "sources": [], "findings": [cov]}
        gaps = [r for r in cov["requirements"] if r["status"] in ("missing", "partial")]
        findings = [
            {
                "requirement": r["code"],
                "title": r["title"],
                "status": r["status"],
                "metric_gap": r["metric_gap"],
                "evidence_gap": r["evidence_gap"],
                "narrative_gap": r["narrative_gap"],
                "missing_metrics": [m["code"] for m in r["metrics"] if not m["has_value"]],
            }
            for r in gaps
        ]
        metrics = [
            {
                "code": f"{fw}.alignment",
                "name": f"{cov['framework_name']} alignment",
                "value": cov["alignment_pct"],
                "unit": "%",
                "period": period or "current",
                "citation": f"[{fw} coverage]",
            },
            {"code": f"{fw}.applicable", "name": "Applicable requirements", "value": cov["applicable"], "citation": f"[{fw} coverage]"},
            {"code": f"{fw}.completed", "name": "Completed requirements", "value": cov["completed"], "citation": f"[{fw} coverage]"},
            {"code": f"{fw}.partial", "name": "Partial requirements", "value": cov["partial"], "citation": f"[{fw} coverage]"},
            {"code": f"{fw}.missing", "name": "Missing requirements", "value": cov["missing"], "citation": f"[{fw} coverage]"},
        ]
        recs = [
            f"{g['requirement']}: {'add metric(s) ' + ', '.join(g['missing_metrics']) if g['missing_metrics'] else ''}{' · link evidence' if g['evidence_gap'] else ''}{' · draft narrative' if g['narrative_gap'] else ''}".strip()
            for g in findings
        ]
        return {
            "title": f"Framework gap analysis — {cov['framework_name']} {cov['version']}",
            "metrics": metrics,
            "sources": [f"[{fw} coverage]"],
            "findings": findings,
            "recommendations": recs,
            "disclaimer": cov["disclaimer"],
            "framework": fw,
        }

    @staticmethod
    def _framework_in(text: str) -> str | None:
        t = (text or "").lower()
        for key, code in (
            ("ifrs", "IFRS_S"),
            ("issb", "IFRS_S"),
            ("gri", "GRI"),
            ("esrs", "ESRS"),
            ("csrd", "ESRS"),
            ("sasb", "SASB_CHEM"),
            ("wef", "WEF_SCM"),
            ("stakeholder capitalism", "WEF_SCM"),
            ("ungc", "UNGC"),
            ("global compact", "UNGC"),
            ("sdg", "UN_SDG"),
        ):
            if key in t:
                return code
        return None

    def compose(self, task, payload, facts, llm_text):
        return {
            "answer": llm_text or "",
            "framework": facts.get("framework"),
            "gaps": facts.get("findings", []),
            "recommendations": facts.get("recommendations", []),
            "disclaimer": facts.get("disclaimer"),
        }


class MaterialityAgent(BaseAgent):
    spec = AgentSpec(
        "materiality_agent",
        "Materiality Agent",
        "Analyses material topics, supports impact and financial materiality, produces recommendations with evidence.",
        ["Analyze material topics", "Assist with impact assessment", "Assist with financial materiality", "Produce recommendations", "Show evidence/reasoning"],
        ["get_metric", "get_metric_history", "search_knowledge_base", "get_open_issues"],
        expert="esg",
    )

    def gather(self, task: str, payload: dict) -> dict:
        assessment = (
            self.db.execute(select(MaterialityAssessment).where(MaterialityAssessment.tenant_id == self.principal.tenant_id).order_by(MaterialityAssessment.id.desc()))
            .scalars()
            .first()
        )
        if assessment is None:
            return {"title": "Materiality", "metrics": [], "sources": [], "findings": [{"error": "No materiality assessment"}]}
        topics = self.db.execute(select(MaterialityTopic).where(MaterialityTopic.assessment_id == assessment.id)).scalars().all()
        metrics, findings, recs = [], [], []
        for t in topics:
            metrics.append(
                {
                    "code": f"materiality.{t.topic_code}",
                    "name": f"{t.name} impact score",
                    "value": t.impact_score,
                    "unit": "/5",
                    "citation": "[KB-REPORT-2023 p.37-38]",
                    "material": t.is_material,
                }
            )
            metrics.append(
                {
                    "code": f"materiality.{t.topic_code}.financial",
                    "name": f"{t.name} financial score",
                    "value": t.financial_score,
                    "unit": "/5",
                    "citation": "[KB-REPORT-2023 p.37-38]",
                }
            )
            missing = []
            for code in t.related_metric_codes or []:
                m = self.tool("get_metric", metric_code=code, period_code=payload.get("period_code", ""))
                if isinstance(m, dict) and m.get("data_unavailable"):
                    missing.append(code)
            if missing:
                findings.append({"topic": t.topic_code, "type": "metric_gap", "missing_metrics": missing})
            if not t.is_material and (t.impact_score or 0) >= assessment.threshold * 0.8:
                recs.append(f"{t.name}: impact score {t.impact_score} is close to the threshold {assessment.threshold} — consider elevating to material in the next cycle.")
        recs.append("The assessment scores impact materiality only; add financial-materiality scoring per topic to support IFRS S1 / ESRS double materiality.")
        return {
            "title": assessment.name,
            "metrics": metrics,
            "sources": ["[KB-REPORT-2023 p.37-38]"],
            "findings": findings,
            "recommendations": recs,
            "threshold": assessment.threshold,
        }

    def compose(self, task, payload, facts, llm_text):
        return {"answer": llm_text or "", "findings": facts.get("findings", []), "recommendations": facts.get("recommendations", [])}


class EvidenceAgent(BaseAgent):
    spec = AgentSpec(
        "evidence_agent",
        "Evidence Agent",
        "Finds relevant evidence, links evidence to metrics, detects unsupported claims and evidence gaps.",
        ["Find relevant evidence", "Link evidence to metrics", "Detect unsupported claims", "Identify evidence gaps"],
        ["get_evidence", "search_knowledge_base", "get_metric", "search_metrics", "get_open_issues"],
        expert="data_quality",
    )

    def gather(self, task: str, payload: dict) -> dict:
        q = payload.get("question", "")
        codes = payload.get("metric_codes") or CODE_RE.findall(q)
        entity = payload.get("entity_code") or _entity_in(q)
        period = payload.get("period_code") or (_periods_in(q) or [""])[0]
        metrics, findings, sources, suggestions = [], [], [], []
        if task == "find_gaps" or not codes:
            issues = self.tool("get_open_issues", severity="", metric_code="", limit=50)
            gaps = [i for i in issues if i["category"] == "evidence_gap"] if isinstance(issues, list) else []
            for g in gaps[:25]:
                findings.append({"metric": g["metric"], "entity": g["entity"], "period": g["period"], "severity": g["severity"], "required_action": g["required_action"]})
            metrics.append({"code": "evidence.gaps", "name": "Open evidence gaps", "value": len(gaps), "citation": "[issues]"})
            sources.append("[issues]")
        for code in codes[:5]:
            ev = self.tool("get_evidence", metric_code=code, entity_code=entity, period_code=period)
            gm = self.tool("get_metric", metric_code=code, entity_code=entity, period_code=period)
            if isinstance(gm, dict) and "error" not in gm:
                metrics.append(gm)
            n = len(ev) if isinstance(ev, list) else 0
            metrics.append({"code": f"{code}.evidence_count", "name": f"Evidence items for {code}", "value": n, "citation": f"[{code} evidence]"})
            for e in (ev if isinstance(ev, list) else [])[:5]:
                sources.append(f"[{e['code']} p.{e.get('printed_page')}]" if e.get("printed_page") else f"[{e['code']}]")
            if n == 0:
                name = gm.get("name", code) if isinstance(gm, dict) else code
                kb = self.tool("search_knowledge_base", query=name, limit=3, kind="report")
                suggestions.append({"metric": code, "candidates": [{"citation": h["citation"], "text": h["text"][:200]} for h in kb] if isinstance(kb, list) else []})
                findings.append({"metric": code, "type": "evidence_gap", "detail": "No evidence linked; candidate report pages suggested."})
        return {"title": "Evidence review", "metrics": metrics, "sources": list(dict.fromkeys(sources)), "findings": findings, "suggestions": suggestions}

    def compose(self, task, payload, facts, llm_text):
        return {"answer": llm_text or "", "findings": facts.get("findings", []), "suggestions": facts.get("suggestions", [])}


class GovernanceAgent(BaseAgent):
    spec = AgentSpec(
        "governance_agent",
        "Governance Agent",
        "Checks governance rules and policies, enforces approvals, detects violations and escalates critical events.",
        ["Check governance rules", "Check policies", "Enforce approval requirements", "Detect policy violations", "Escalate critical events"],
        ["run_governance_check", "get_open_issues", "get_report_readiness", "search_knowledge_base"],
        expert="governance",
    )

    def gather(self, task: str, payload: dict) -> dict:
        q = payload.get("question", "")
        codes = payload.get("metric_codes") or CODE_RE.findall(q)
        entity = payload.get("entity_code") or _entity_in(q)
        period = payload.get("period_code") or (_periods_in(q) or [""])[0]
        metrics, findings = [], []
        for code in codes[:5]:
            chk = self.tool("run_governance_check", metric_code=code, entity_code=entity, period_code=period)
            if isinstance(chk, dict) and "error" not in chk:
                for t in chk["triggered"]:
                    findings.append({"metric": code, **t})
                metrics.append({"code": f"{code}.rules_triggered", "name": f"Rules triggered for {code}", "value": len(chk["triggered"]), "citation": f"[governance {code}]"})
        issues = self.tool("get_open_issues", severity=payload.get("severity", ""), limit=30)
        crit = [i for i in issues if i["severity"] == "CRITICAL"] if isinstance(issues, list) else []
        metrics.append({"code": "issues.open", "name": "Open issues", "value": len(issues) if isinstance(issues, list) else 0, "citation": "[issues]"})
        metrics.append({"code": "issues.critical", "name": "Critical issues", "value": len(crit), "citation": "[issues]"})
        for i in (issues if isinstance(issues, list) else [])[:15]:
            findings.append(i)
        escalations = [f"ESCALATE {i['code']}: {i['title']}" for i in crit]
        return {"title": "Governance check", "metrics": metrics, "sources": ["[issues]", "[governance rules]"], "findings": findings, "escalations": escalations}

    def compose(self, task, payload, facts, llm_text):
        return {"answer": llm_text or "", "findings": facts.get("findings", []), "escalations": facts.get("escalations", [])}


class RAGResearchAgent(BaseAgent):
    spec = AgentSpec(
        "rag_research_agent",
        "RAG Research Agent",
        "Retrieves approved ESG knowledge, policies, framework requirements, historical reports and internal documentation — permission-aware, with citations.",
        [
            "Retrieve approved ESG knowledge",
            "Retrieve organizational policies",
            "Retrieve framework requirements",
            "Retrieve historical reports",
            "Retrieve internal documentation",
        ],
        [
            "search_knowledge_base",
            "search_metrics",
            "get_metric",
            "get_metric_history",
            "get_framework_mapping",
            "get_open_issues",
            "get_report_readiness",
            "get_evidence",
            "calculate_metric",
            "list_entities",
        ],
        expert="esg",
    )

    def gather(self, task: str, payload: dict) -> dict:
        q = payload.get("question", "")
        entity = payload.get("entity_code") or _entity_in(q)
        periods = _periods_in(q) or [payload.get("period_code") or ""]
        metrics, sources, passages = [], [], []
        codes = CODE_RE.findall(q)
        if not codes:
            hits = self.tool("search_metrics", query=q, limit=payload.get("max_metrics", 5))
            codes = [h["code"] for h in hits] if isinstance(hits, list) else []
        for code in codes[:6]:
            for period in periods[:2]:
                gm = self.tool("get_metric", metric_code=code, entity_code=entity, period_code=period)
                if isinstance(gm, dict) and "error" not in gm:
                    metrics.append(gm)
                    sources.append(gm["citation"])
                    for e in gm.get("evidence", [])[:2]:
                        sources.append(f"[{e}]")
        if re.search(r"\b(why|trend|chang|increas|decreas|compar|history|over time)\b", q, re.I) and codes:
            hist = self.tool("get_metric_history", metric_code=codes[0], entity_code=entity)
            if isinstance(hist, dict) and "error" not in hist:
                for s in hist["series"]:
                    if s["value"] is not None:
                        metrics.append(
                            {
                                "code": hist["code"],
                                "name": hist["name"],
                                "unit": hist["unit"],
                                "period": s["period"],
                                "value": s["value"],
                                "citation": f"[{hist['code']} · {hist['entity']} · {s['period']}]",
                            }
                        )
        kb = self.tool("search_knowledge_base", query=q, limit=payload.get("max_passages", 4))
        for h in kb if isinstance(kb, list) else []:
            passages.append({"citation": h["citation"], "text": h["text"][:700], "kind": h["kind"], "freshness": h.get("freshness")})
            sources.append(h["citation"])
        if re.search(r"\b(ready|readiness|publish|missing|prevent|block)\b", q, re.I):
            rd = self.tool("get_report_readiness", period_code=periods[0])
            if isinstance(rd, dict) and "error" not in rd:
                metrics.append({"code": "readiness.overall", "name": "Report readiness", "value": rd["overall"], "unit": "%", "citation": "[readiness]"})
                for k, v in rd["components"].items():
                    metrics.append({"code": f"readiness.{k}", "name": k.replace("_", " "), "value": v, "unit": "%", "citation": "[readiness]"})
                passages.append({"citation": "[readiness]", "text": " ".join(rd["explanation"]), "kind": "readiness"})
                for b in rd["blocking_issues"][:5]:
                    passages.append({"citation": f"[{b['code']}]", "text": f"{b['severity']}: {b['title']} — {b.get('required_action') or ''}", "kind": "issue"})
                sources.append("[readiness]")
        if re.search(r"\b(incomplete|gap|coverage|alignment|disclosure)\b", q, re.I):
            fw = StandardsMappingAgent._framework_in(q) or "WEF_SCM"
            cov = self.tool("get_framework_mapping", framework_code=fw, period_code=periods[0])
            if isinstance(cov, dict) and "error" not in cov:
                metrics.append(
                    {"code": f"{fw}.alignment", "name": f"{cov['framework_name']} alignment", "value": cov["alignment_pct"], "unit": "%", "citation": f"[{fw} coverage]"}
                )
                for r in [r for r in cov["requirements"] if r["status"] in ("missing", "partial")][:8]:
                    passages.append(
                        {
                            "citation": f"[{r['code']}]",
                            "text": f"{r['title']} — {r['status']}; missing metrics: {', '.join(m['code'] for m in r['metrics'] if not m['has_value']) or 'none'}",
                            "kind": "requirement",
                        }
                    )
                sources.append(f"[{fw} coverage]")
        return {"title": None, "metrics": metrics, "sources": list(dict.fromkeys(s for s in sources if s)), "passages": passages}

    def prompt(self, task, payload, facts):
        return payload.get("question", "Answer the ESG question using only the facts.")

    def compose(self, task, payload, facts, llm_text):
        return {"answer": llm_text or "", "passages": facts.get("passages", []), "metrics": facts.get("metrics", [])}


class ReportingAgent(BaseAgent):
    spec = AgentSpec(
        "reporting_agent",
        "Reporting Agent",
        "Assembles report sections and generates formal narratives referencing approved metrics and evidence.",
        ["Assemble report sections", "Generate narratives", "Reference approved metrics", "Reference evidence", "Maintain formal language", "Never fabricate unsupported claims"],
        ["get_metric", "get_metric_history", "get_evidence", "search_knowledge_base", "get_framework_requirement"],
        expert="report_writing",
    )

    def gather(self, task: str, payload: dict) -> dict:
        codes: list[str] = payload.get("metric_codes") or []
        entity = payload.get("entity_code") or ""
        period = payload.get("period_code") or ""
        metrics, sources, passages = [], [], []
        for code in codes[:20]:
            gm = self.tool("get_metric", metric_code=code, entity_code=entity, period_code=period)
            if isinstance(gm, dict) and "error" not in gm:
                metrics.append(gm)
                sources.append(gm["citation"])
                for e in gm.get("evidence", [])[:1]:
                    sources.append(f"[{e}]")
        for rc in (payload.get("requirement_codes") or [])[:5]:
            req = self.tool("get_framework_requirement", requirement_code=rc, period_code=period)
            if isinstance(req, dict) and "error" not in req:
                passages.append({"citation": f"[{rc}]", "text": f"{req['title']}: {req.get('description') or ''} (status: {req['status']})", "kind": "requirement"})
        if payload.get("title"):
            kb = self.tool("search_knowledge_base", query=payload["title"], limit=3, kind="report")
            for h in kb if isinstance(kb, list) else []:
                passages.append({"citation": h["citation"], "text": h["text"][:600], "kind": "report"})
                sources.append(h["citation"])
        return {"title": payload.get("title"), "metrics": metrics, "sources": list(dict.fromkeys(sources)), "passages": passages}

    def prompt(self, task, payload, facts):
        return (
            f"Draft the report section '{payload.get('title', 'Section')}' for reporting period {payload.get('period_code', 'current')}. "
            "Write 2–4 formal paragraphs: state each governed metric with its value, unit, period and citation; compare with the prior period where available; "
            "note evidence status and explicitly mark missing values as 'Data unavailable'. Do not add figures that are not in FACTS."
        )

    def evaluation_query(self, task, payload, facts):
        names = " ".join(m.get("name", "") for m in facts.get("metrics", []) if isinstance(m, dict))
        return f"{payload.get('title', '')} {payload.get('period_code', '')} {names}"

    def compose(self, task, payload, facts, llm_text):
        return {"narrative": llm_text or "", "answer": llm_text or "", "metrics": facts.get("metrics", []), "sources": facts.get("sources", [])}


class EvaluationAgent(BaseAgent):
    spec = AgentSpec(
        "evaluation_agent",
        "Evaluation Agent",
        "Evaluates AI outputs for factual, numerical and citation consistency, framework compliance and hallucination; assigns confidence.",
        [
            "Evaluate AI outputs",
            "Check factual consistency",
            "Check citation/provenance",
            "Check numerical consistency",
            "Check framework compliance",
            "Detect hallucinations",
            "Assign confidence",
        ],
        ["get_metric", "search_knowledge_base"],
        expert="data_quality",
        narrative=False,
    )

    def gather(self, task: str, payload: dict) -> dict:
        from app.ai.agents.evaluation import score_output

        text = payload.get("text", "")
        facts = payload.get("facts") or {"metrics": [], "sources": []}
        if not facts.get("metrics"):
            for code in CODE_RE.findall(text)[:10]:
                gm = self.tool("get_metric", metric_code=code, entity_code=payload.get("entity_code", ""), period_code=payload.get("period_code", ""))
                if isinstance(gm, dict) and "error" not in gm:
                    facts.setdefault("metrics", []).append(gm)
        from app.ai import guardrails as g

        allowed = [m["value"] for m in facts.get("metrics", []) if isinstance(m, dict) and isinstance(m.get("value"), (int, float))]
        guard = g.check_output(text, allowed_numbers=allowed, sources=facts.get("sources"), require_citations=True)
        ev = score_output(text, facts=facts, question=payload.get("question", ""), guard=guard)
        return {"title": "Evaluation", "metrics": [], "sources": [], "evaluation": ev, "guardrail": guard.as_dict(), "findings": ev["findings"]}

    def compose(self, task, payload, facts, llm_text):
        return {"evaluation": facts["evaluation"], "guardrail": facts["guardrail"], "confidence": round(facts["evaluation"]["overall"] / 100, 2)}


class AssuranceAgent(BaseAgent):
    spec = AgentSpec(
        "assurance_agent",
        "Assurance Agent",
        "Identifies disclosure gaps, unsupported metrics, inconsistent calculations and unresolved issues; prepares assurance-ready packages.",
        [
            "Identify disclosure gaps",
            "Identify unsupported metrics",
            "Identify inconsistent calculations",
            "Identify unresolved validation issues",
            "Prepare assurance-ready evidence packages",
        ],
        ["get_open_issues", "get_report_readiness", "get_framework_mapping", "run_data_quality_check", "get_evidence", "get_lineage"],
        expert="risk",
    )

    def gather(self, task: str, payload: dict) -> dict:
        period = payload.get("period_code", "")
        fws = payload.get("frameworks") or ["WEF_SCM", "UNGC", "UN_SDG"]
        rd = self.tool("get_report_readiness", period_code=period, framework_codes=",".join(fws))
        issues = self.tool("get_open_issues", limit=100)
        metrics = [{"code": "readiness.overall", "name": "Report readiness", "value": rd.get("overall"), "unit": "%", "citation": "[readiness]"}]
        for k, v in (rd.get("components") or {}).items():
            metrics.append({"code": f"readiness.{k}", "name": k.replace("_", " "), "value": v, "unit": "%", "citation": "[readiness]"})
        findings = []
        for fw in fws:
            cov = self.tool("get_framework_mapping", framework_code=fw, period_code=period)
            if isinstance(cov, dict) and "error" not in cov:
                metrics.append({"code": f"{fw}.alignment", "name": f"{fw} alignment", "value": cov["alignment_pct"], "unit": "%", "citation": f"[{fw} coverage]"})
                for r in cov["requirements"]:
                    if r["status"] in ("missing", "partial"):
                        findings.append(
                            {
                                "type": "disclosure_gap",
                                "framework": fw,
                                "requirement": r["code"],
                                "status": r["status"],
                                "missing_metrics": [m["code"] for m in r["metrics"] if not m["has_value"]],
                            }
                        )
        # inconsistent calculations: quality explanations mentioning differences
        from app.models.ai import QualityScore

        qs = self.db.execute(select(QualityScore).where(QualityScore.tenant_id == self.principal.tenant_id, QualityScore.consistency < 100)).scalars().all()
        for q in qs[:40]:
            md = self.db.get(MetricDefinition, q.metric_id)
            ent = self.db.get(Entity, q.entity_id)
            findings.append(
                {
                    "type": "inconsistent_calculation",
                    "metric": md.code if md else q.metric_id,
                    "entity": ent.code if ent else q.entity_id,
                    "consistency": q.consistency,
                    "detail": [e for e in (q.explanation or []) if "differs" in e or "exceeds" in e],
                }
            )
        for i in issues if isinstance(issues, list) else []:
            findings.append({"type": "unresolved_issue", **i})
        metrics.append({"code": "issues.open", "name": "Unresolved issues", "value": len(issues) if isinstance(issues, list) else 0, "citation": "[issues]"})
        package = {
            "period": period or "current",
            "frameworks": fws,
            "readiness": rd,
            "disclosure_gaps": [f for f in findings if f["type"] == "disclosure_gap"],
            "inconsistent_calculations": [f for f in findings if f["type"] == "inconsistent_calculation"],
            "unresolved_issues": [f for f in findings if f["type"] == "unresolved_issue"],
        }
        return {
            "title": "Assurance readiness package",
            "metrics": metrics,
            "sources": ["[readiness]", "[issues]"] + [f"[{fw} coverage]" for fw in fws],
            "findings": findings,
            "package": package,
        }

    def compose(self, task, payload, facts, llm_text):
        return {"answer": llm_text or "", "package": facts.get("package"), "findings": facts.get("findings", [])}
