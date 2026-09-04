"""Report Builder.

create → generate_draft (data sections deterministic, narrative sections via Reporting Agent + evaluation)
→ validate (nine pre-generation checks; critical failures block) → review/approve sections → generate final
(PDF/DOCX/XLSX/CSV) with governance gate and audit trail.
"""

from __future__ import annotations

import contextlib
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.agents import registry as agent_registry
from app.core import audit
from app.core.config import get_settings
from app.core.errors import GovernanceBlockedError, NotFoundError
from app.core.security import Principal
from app.engines import frameworks as fw_engine
from app.engines import metric_engine
from app.engines.readiness import compute as compute_readiness
from app.models.esg import MetricDefinition, MetricValue, Target
from app.models.evidence import Evidence
from app.models.organization import Entity, Organization, ReportingPeriod
from app.models.reporting import Report, ReportSection, ReportVersion
from app.reports.renderers import csv_renderer, docx_renderer, html_renderer, pdf_renderer, xlsx_renderer
from app.reports.templates import get_template
from app.services.governance_service import check_report

RENDERERS = {"pdf": pdf_renderer.render, "docx": docx_renderer.render, "xlsx": xlsx_renderer.render, "csv": csv_renderer.render, "html": html_renderer.render}


def _fmt(v: Any, unit: str | None = None) -> str:
    if v is None:
        return "Data unavailable"
    if isinstance(v, float):
        s = f"{v:,.0f}" if abs(v) >= 1000 else (f"{v:,.2f}".rstrip("0").rstrip(".") if not float(v).is_integer() else f"{int(v):,}")
    elif isinstance(v, int):
        s = f"{v:,}"
    else:
        return str(v)
    return f"{s} {unit}".strip() if unit else s


class ReportBuilder:
    def __init__(self, db: Session, principal: Principal):
        self.db = db
        self.principal = principal
        self.settings = get_settings()

    # ------------------------------------------------------------------ lookup helpers
    def report(self, report_id: int) -> Report:
        r = self.db.get(Report, report_id)
        if r is None or r.tenant_id != self.principal.tenant_id:
            raise NotFoundError("Report not found")
        return r

    def _group(self, org_id: int) -> Entity:
        return self.db.execute(select(Entity).where(Entity.organization_id == org_id, Entity.kind == "group")).scalars().first()

    def _metric(self, code: str) -> MetricDefinition | None:
        return self.db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == self.principal.tenant_id, MetricDefinition.code == code)).scalars().first()

    def _value(self, metric: MetricDefinition, entity: Entity, period: ReportingPeriod) -> dict:
        mv = (
            self.db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == period.id)).scalars().first()
        )
        value = None
        if mv is not None:
            value = mv.value_numeric if mv.value_numeric is not None else mv.value_text
        if value is None:
            v, _ = metric_engine.get_value(self.db, self.principal.tenant_id, metric.code, entity, period)
            value = v
        from app.engines.evidence_resolution import evidence_codes

        ev = evidence_codes(self.db, metric, entity, period, mv) if value is not None else []
        return {
            "code": metric.code,
            "name": metric.name,
            "unit": metric.unit,
            "value": value,
            "status": mv.status if mv else ("consolidated" if value is not None else "unavailable"),
            "evidence": ev,
            "kind": metric.kind,
            "is_estimate": bool(mv.is_estimate) if mv else False,
        }

    # ------------------------------------------------------------------ create
    def create(self, *, organization_id: int, period_id: int, template_code: str, title: str | None, framework_codes: list[str], scope: dict | None = None) -> Report:
        tpl = get_template(template_code)
        if tpl is None:
            raise NotFoundError(f"Template {template_code} not found")
        org = self.db.get(Organization, organization_id)
        period = self.db.get(ReportingPeriod, period_id)
        report = Report(
            tenant_id=self.principal.tenant_id,
            organization_id=organization_id,
            period_id=period_id,
            template_code=template_code,
            title=title or f"{org.name} — {tpl['name']} {period.label}",
            framework_codes=framework_codes,
            scope=scope or {},
            status="draft",
            created_by=self.principal.user_id,
        )
        self.db.add(report)
        self.db.flush()
        applicable = self._applicable_sections(tpl, framework_codes)
        for i, s in enumerate(applicable):
            self.db.add(
                ReportSection(
                    report_id=report.id,
                    code=s["code"],
                    title=s["title"],
                    sort_order=i,
                    level=s.get("level", 1),
                    narrative_source=s.get("source", "template"),
                    status="draft",
                    metric_codes=s.get("metrics", []),
                    requirement_codes=s.get("requirements", []),
                    tables=[],
                    charts=[s["chart"]] if s.get("chart") else [],
                )
            )
        self.db.flush()
        audit.record(
            self.db,
            tenant_id=self.principal.tenant_id,
            user_id=self.principal.user_id,
            action="report.create",
            object_type="report",
            object_id=report.id,
            new_value={"title": report.title, "template": template_code, "frameworks": framework_codes},
        )
        return report

    def _applicable_sections(self, tpl: dict, framework_codes: list[str]) -> list[dict]:
        """Sections change dynamically with framework selection: keep a section if it has no requirements, or at least one requirement belongs to a selected framework, or it is structural."""
        prefixes = {c.split("_")[0] for c in framework_codes} | {"UN" if "UN_SDG" in framework_codes else ""}
        out = []
        for s in tpl["sections"]:
            reqs = s.get("requirements") or []
            if not reqs or s.get("source") in ("template", "data") or any(r.split(".")[0] in prefixes or (r.startswith("SDG") and "UN_SDG" in framework_codes) for r in reqs):
                out.append(s)
        return out

    # ------------------------------------------------------------------ draft generation
    def generate_draft(self, report_id: int, *, sections: list[str] | None = None) -> Report:
        report = self.report(report_id)
        if report.locked:
            raise GovernanceBlockedError("Report is locked (approved/published). Create a new version instead.")
        period = self.db.get(ReportingPeriod, report.period_id)
        group = self._group(report.organization_id)
        for section in report.sections:
            if sections and section.code not in sections:
                continue
            self._build_section(report, section, period, group)
            section.version += 1
        report.status = "ai_generated"
        report.readiness = compute_readiness(self.db, self.principal.tenant_id, report.organization_id, period, framework_codes=report.framework_codes, report=report).__dict__
        self.db.flush()
        audit.record(
            self.db,
            tenant_id=self.principal.tenant_id,
            user_id=self.principal.user_id,
            action="report.generate_draft",
            object_type="report",
            object_id=report.id,
            new_value={"sections": sections or "all"},
        )
        return report

    def _build_section(self, report: Report, section: ReportSection, period: ReportingPeriod, group: Entity) -> None:
        tpl_section = next((s for s in (get_template(report.template_code) or {"sections": []})["sections"] if s["code"] == section.code), {})
        prev = metric_engine.previous_period(self.db, period)
        rows = []
        for code in section.metric_codes or []:
            m = self._metric(code)
            if m is None:
                continue
            cur = self._value(m, group, period)
            pv = self._value(m, group, prev)["value"] if prev else None
            rows.append({**cur, "previous": pv, "previous_period": prev.code if prev else None})
        section.tables = (
            [
                {
                    "title": f"{section.title} — key metrics ({period.code})",
                    "columns": ["Metric", period.code, prev.code if prev else "Prior", "Unit", "Evidence"],
                    "rows": [[r["name"], _fmt(r["value"]), _fmt(r["previous"]), r["unit"] or "", ", ".join(r["evidence"][:3])] for r in rows],
                }
            ]
            if rows
            else []
        )
        tcfg = tpl_section.get("table")
        if tcfg and tcfg.get("by_entity"):
            section.tables.append(self._entity_table(tcfg["metrics"], period, report.organization_id))
        section.evidence_codes = sorted({e for r in rows for e in r["evidence"]})
        source = section.narrative_source
        if source == "ai":
            agent = agent_registry.get("reporting_agent")(self.db, self.principal)
            res = agent.run(
                "draft_section",
                {
                    "title": section.title,
                    "metric_codes": section.metric_codes,
                    "requirement_codes": section.requirement_codes,
                    "period_code": period.code,
                    "entity_code": group.code,
                    "frameworks": report.framework_codes,
                },
            )
            section.content_md = res.output.get("narrative") or ""
            section.agent_run_id = res.run_id
            if res.evaluation:
                from app.models.ai import Evaluation

                ev = self.db.execute(select(Evaluation).where(Evaluation.object_type == "agent_run", Evaluation.object_id == str(res.run_id))).scalars().first()
                section.evaluation_id = ev.id if ev else None
            section.status = "blocked" if res.blocked else ("requires_review" if res.requires_human_review else "ai_generated")
            section.comments = (section.comments or []) + [
                {
                    "at": datetime.now(UTC).isoformat(),
                    "by": "reporting_agent",
                    "note": f"Draft generated (confidence {res.confidence}); governance: {[g['rule'] for g in res.governance]}",
                }
            ]
        elif source == "data":
            section.content_md = self._data_section(section.code, report, period, group)
            section.status = "requires_review"
        else:
            section.content_md = section.content_md or ""
            section.status = "requires_review" if section.code != "cover" else "approved"
            if section.code == "cover":
                section.content_md = f"# {report.title}\n\nReporting period: {period.label} ({period.start_date} – {period.end_date})\n\nFrameworks: {', '.join(report.framework_codes)}\n\nStatus: {report.status}"

    def _entity_table(self, codes: list[str], period: ReportingPeriod, org_id: int) -> dict:
        metrics = [self._metric(c) for c in codes]
        metrics = [m for m in metrics if m]
        entities = self.db.execute(select(Entity).where(Entity.organization_id == org_id, Entity.in_reporting_boundary.is_(True)).order_by(Entity.code)).scalars().all()
        rows = []
        for e in entities:
            vals = [self._value(m, e, period)["value"] for m in metrics]
            if any(v is not None for v in vals) and e.kind != "group":
                rows.append([e.code] + [_fmt(v) for v in vals])
        group = next((e for e in entities if e.kind == "group"), None)
        if group:
            rows.append(["Group (consolidated)"] + [_fmt(self._value(m, group, period)["value"]) for m in metrics])
        return {"title": f"By entity — {period.code}", "columns": ["Entity"] + [f"{m.name} ({m.unit or ''})" for m in metrics], "rows": rows}

    def _data_section(self, code: str, report: Report, period: ReportingPeriod, group: Entity) -> str:
        if code == "targets":
            lines = ["| Metric | Entity | Target | Direction | Year | Status | Description |", "|---|---|---|---|---|---|---|"]
            for t in self.db.execute(select(Target).where(Target.tenant_id == self.principal.tenant_id)).scalars().all():
                m, e = self.db.get(MetricDefinition, t.metric_id), self.db.get(Entity, t.entity_id)
                lines.append(
                    f"| {m.name} | {e.code} | {_fmt(t.target_value, m.unit) if t.target_value is not None else 'Not set'} | {t.direction} | {t.target_year or '—'} | {t.status} | {t.description or ''} |"
                )
            return "\n".join(lines)
        if code == "framework_index":
            out = []
            for fw in report.framework_codes:
                cov = fw_engine.coverage(self.db, self.principal.tenant_id, report.organization_id, period, fw)
                out.append(f"## {cov.get('framework_name', fw)} ({cov.get('version', '')}) — alignment {cov['alignment_pct']}%\n")
                out.append("| Requirement | Title | Status | Metrics | Report section |\n|---|---|---|---|---|")
                for r in cov["requirements"]:
                    secs = [s.title for s in report.sections if r["code"] in (s.requirement_codes or [])]
                    out.append(f"| {r['code']} | {r['title']} | {r['status']} | {', '.join(m['code'] for m in r['metrics'])} | {'; '.join(secs) or '—'} |")
                out.append(f"\n_{cov['disclaimer']}_\n")
            return "\n".join(out)
        if code == "methodology":
            codes = sorted({c for s in report.sections for c in (s.metric_codes or [])})
            lines = ["| Code | Metric | Unit | Kind | Formula / method | Assurance |", "|---|---|---|---|---|---|"]
            for c in codes:
                m = self._metric(c)
                if m:
                    lines.append(f"| {m.code} | {m.name} | {m.unit or ''} | {m.kind} | {m.formula or (m.calculation_method or '')} | {m.assurance_status} |")
            return "Metric definitions, formulas (deterministic engine, versioned) and assurance status.\n\n" + "\n".join(lines)
        if code == "assurance":
            ev = self.db.execute(select(Evidence).where(Evidence.tenant_id == self.principal.tenant_id, Evidence.kind == "assurance_statement")).scalars().first()
            if ev:
                return f"{ev.title}\n\nStatus: {ev.verification_status}; confidence {ev.confidence}.\n\n{ev.excerpt or ''}\n\nThe platform reports framework alignment and readiness; it does not itself provide assurance."
            return "No assurance statement on file. Evidence required."
        if code == "appendix":
            codes = sorted({c for s in report.sections for c in (s.metric_codes or [])})
            lines = ["| Code | Metric | Value | Unit | Status | Evidence |", "|---|---|---|---|---|---|"]
            for c in codes:
                m = self._metric(c)
                if m:
                    v = self._value(m, group, period)
                    lines.append(f"| {m.code} | {m.name} | {_fmt(v['value'])} | {m.unit or ''} | {v['status']} | {', '.join(v['evidence'][:4])} |")
            return "\n".join(lines)
        return ""

    # ------------------------------------------------------------------ validation (nine checks)
    def validate(self, report_id: int) -> dict:
        report = self.report(report_id)
        period = self.db.get(ReportingPeriod, report.period_id)
        group = self._group(report.organization_id)
        checks: list[dict] = []

        def add(name, passed, detail, severity="HIGH"):
            checks.append({"check": name, "passed": bool(passed), "detail": detail, "severity": severity if not passed else "INFO"})

        # 1 data validation — every section metric has a value or an explicit unavailable marker
        missing = []
        for s in report.sections:
            for c in s.metric_codes or []:
                m = self._metric(c)
                if m and self._value(m, group, period)["value"] is None and m.kind != "narrative":
                    missing.append(c)
        add("data_validation", len(missing) <= 3, f"{len(missing)} metric(s) without values: {', '.join(missing[:8])}", "MEDIUM")
        # 2 metric validation — derived metrics recalculated ok
        bad = [c.metric_code for c in metric_engine.recalculate_all(self.db, self.principal.tenant_id, report.organization_id, period) if c.status == "error"]
        add("metric_validation", not bad, f"{len(bad)} calculation error(s)")
        # 3 framework validation
        aligns = {fw: fw_engine.coverage(self.db, self.principal.tenant_id, report.organization_id, period, fw)["alignment_pct"] for fw in report.framework_codes}
        add("framework_validation", all(a >= 50 for a in aligns.values()), f"alignment: {aligns}", "MEDIUM")
        # 4 evidence validation
        no_ev = []
        for s in report.sections:
            for c in s.metric_codes or []:
                m = self._metric(c)
                if m and m.evidence_required:
                    v = self._value(m, group, period)
                    if v["value"] is not None and not v["evidence"]:
                        no_ev.append(c)
        add("evidence_validation", not no_ev, f"{len(no_ev)} valued metric(s) without evidence: {', '.join(no_ev[:8])}")
        # 5 narrative validation — every ai/data section has content
        empty = [s.code for s in report.sections if s.narrative_source in ("ai", "data") and not (s.content_md or "").strip()]
        add("narrative_validation", not empty, f"empty sections: {empty}")
        # 6 numerical consistency — narrative numbers must be governed
        from app.ai import guardrails

        inconsistent = []
        for s in report.sections:
            if s.narrative_source == "ai" and s.content_md:
                g = guardrails.check_output(s.content_md, allowed_numbers=self._allowed_numbers(s, group, period), sources=["x"], require_citations=False)
                if g.unsupported_numbers:
                    inconsistent.append({"section": s.code, "numbers": g.unsupported_numbers[:5]})
        add("numerical_consistency", not inconsistent, f"{inconsistent}" if inconsistent else "all narrative figures match governed metrics", "CRITICAL")
        # 7 governance validation
        gov = check_report(self.db, self.principal.tenant_id, report)
        add("governance_validation", not gov["blocked"], gov["blocking_reasons"] or "no blocking rules", "CRITICAL")
        # 8 AI evaluation
        from app.models.ai import Evaluation

        evals = [self.db.get(Evaluation, s.evaluation_id) for s in report.sections if s.evaluation_id]
        low = [s.code for s, e in zip([s for s in report.sections if s.evaluation_id], evals, strict=False) if e and e.overall < 70]
        add("ai_evaluation", not low, f"sections below 70: {low}" if low else f"{len(evals)} evaluated section(s) ≥ 70", "MEDIUM")
        # 9 completeness — sections reviewed/approved
        unapproved = [s.code for s in report.sections if s.status not in ("approved", "published")]
        add("report_completeness", not unapproved, f"{len(unapproved)} section(s) not approved: {unapproved[:10]}")

        critical_failed = [c for c in checks if not c["passed"] and c["severity"] == "CRITICAL"]
        blocked = bool(critical_failed)
        result = {
            "blocked": blocked,
            "checks": checks,
            "readiness": gov["readiness"],
            "governance": gov["outcomes"],
            "reason": [c["detail"] for c in critical_failed],
            "required_action": [o["required_action"] for o in gov["outcomes"] if o.get("required_action")],
        }
        report.validation_result = result
        report.readiness = gov["readiness"]
        if report.status not in ("approved", "published"):  # never downgrade an approved/published report
            report.status = "blocked" if blocked else ("requires_review" if unapproved else "reviewed")
        self.db.flush()
        audit.record(
            self.db,
            tenant_id=self.principal.tenant_id,
            user_id=self.principal.user_id,
            action="report.validate",
            object_type="report",
            object_id=report.id,
            new_value={"blocked": blocked, "failed": [c["check"] for c in checks if not c["passed"]]},
        )
        return result

    def _allowed_numbers(self, section: ReportSection, group: Entity, period: ReportingPeriod) -> list[float]:
        """Every figure a narrative may legitimately contain: governed values, prior values, tool-computed YoY, and digits that are part of metric names/units."""
        from app.ai import guardrails

        allowed: list[float] = []
        prev = metric_engine.previous_period(self.db, period)
        for c in section.metric_codes or []:
            m = self._metric(c)
            if m is None:
                continue
            v = self._value(m, group, period)["value"]
            pv = self._value(m, group, prev)["value"] if prev else None
            for txt in (v, pv):
                if isinstance(txt, str):
                    for token in guardrails.NUMBER_RE.finditer(txt):
                        with contextlib.suppress(ValueError):
                            allowed.append(float(token.group(1).replace(",", "")))
            if isinstance(v, (int, float)):
                allowed.append(float(v))
            if isinstance(pv, (int, float)):
                allowed.append(float(pv))
                if isinstance(v, (int, float)) and pv != 0:
                    allowed.append(round((v - pv) / abs(pv) * 100, 1))
            for token in guardrails.NUMBER_RE.finditer(f"{m.name} {m.unit or ''} {m.description or ''}"):
                with contextlib.suppress(ValueError):
                    allowed.append(float(token.group(1).replace(",", "")))
        return allowed

    # ------------------------------------------------------------------ review workflow
    def transition_section(self, report_id: int, section_code: str, state: str, *, comment: str | None = None, content_md: str | None = None) -> ReportSection:
        report = self.report(report_id)
        section = next((s for s in report.sections if s.code == section_code), None)
        if section is None:
            raise NotFoundError("Section not found")
        if not self.principal.can_transition(state):
            from app.core.errors import PermissionError_

            raise PermissionError_(f"Role not permitted to move a section to '{state}'", details={"roles": self.principal.roles})
        old = {"status": section.status}
        if content_md is not None:
            section.content_md = content_md
            section.narrative_source = "human"
            section.version += 1
        section.status = state
        if state == "approved":
            section.approved_by = self.principal.user_id
        section.comments = (section.comments or []) + [{"at": datetime.now(UTC).isoformat(), "by": self.principal.email, "state": state, "note": comment}]
        self.db.flush()
        audit.record(
            self.db,
            tenant_id=self.principal.tenant_id,
            user_id=self.principal.user_id,
            action=f"report_section.{state}",
            object_type="report_section",
            object_id=section.id,
            old_value=old,
            new_value={"status": state},
            reason=comment,
        )
        return section

    def transition_report(self, report_id: int, state: str, *, comment: str | None = None) -> Report:
        report = self.report(report_id)
        if not self.principal.can_transition(state):
            from app.core.errors import PermissionError_

            raise PermissionError_(f"Role not permitted to move a report to '{state}'", details={"roles": self.principal.roles})
        if state in ("approved", "published"):
            result = self.validate(report_id)
            if result["blocked"]:
                raise GovernanceBlockedError("Report generation blocked", details={"reason": result["reason"], "required_action": result["required_action"]})
            unapproved = [s.code for s in report.sections if s.status not in ("approved", "published")]
            if unapproved:
                raise GovernanceBlockedError("All sections must be approved first", details={"sections": unapproved})
        old = report.status
        report.status = state
        if state == "approved":
            report.approved_by = self.principal.user_id
            report.locked = True
        if state == "published":
            report.published_at = datetime.now(UTC)
            report.locked = True
            for s in report.sections:
                s.status = "published"
        self.db.flush()
        audit.record(
            self.db,
            tenant_id=self.principal.tenant_id,
            user_id=self.principal.user_id,
            action=f"report.{state}",
            object_type="report",
            object_id=report.id,
            old_value={"status": old},
            new_value={"status": state},
            reason=comment,
        )
        return report

    # ------------------------------------------------------------------ rendering
    def render_payload(self, report_id: int) -> dict:
        report = self.report(report_id)
        org = self.db.get(Organization, report.organization_id)
        period = self.db.get(ReportingPeriod, report.period_id)
        return {
            "title": report.title,
            "organization": org.name,
            "period": period.label,
            "period_code": period.code,
            "frameworks": report.framework_codes,
            "status": report.status,
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            "readiness": report.readiness or {},
            "sections": [
                {
                    "code": s.code,
                    "title": s.title,
                    "level": s.level,
                    "content_md": s.content_md or "",
                    "tables": s.tables or [],
                    "status": s.status,
                    "metric_codes": s.metric_codes or [],
                    "evidence_codes": s.evidence_codes or [],
                    "requirement_codes": s.requirement_codes or [],
                    "source": s.narrative_source,
                }
                for s in report.sections
            ],
            "metric_rows": self._appendix_rows(report, period),
        }

    def _appendix_rows(self, report: Report, period: ReportingPeriod) -> list[dict]:
        group = self._group(report.organization_id)
        prev = metric_engine.previous_period(self.db, period)
        rows = []
        for c in sorted({c for s in report.sections for c in (s.metric_codes or [])}):
            m = self._metric(c)
            if m is None:
                continue
            v = self._value(m, group, period)
            pv = self._value(m, group, prev)["value"] if prev else None
            rows.append(
                {
                    "code": m.code,
                    "name": m.name,
                    "pillar": m.pillar,
                    "unit": m.unit,
                    "value": v["value"],
                    "previous": pv,
                    "status": v["status"],
                    "evidence": v["evidence"],
                    "kind": m.kind,
                    "assurance": m.assurance_status,
                }
            )
        return rows

    def generate(self, report_id: int, fmt: str, *, final: bool = False) -> ReportVersion:
        report = self.report(report_id)
        if fmt not in RENDERERS:
            raise NotFoundError(f"Unsupported format {fmt}")
        if final:
            result = self.validate(report_id)
            if result["blocked"]:
                raise GovernanceBlockedError("Report generation blocked", details={"reason": result["reason"], "required_action": result["required_action"]})
            if report.status not in ("approved", "published"):
                raise GovernanceBlockedError(
                    "Final generation requires an approved report",
                    details={"status": report.status, "required_action": "Approve the report (Report Approver) before generating the final document."},
                )
        payload = self.render_payload(report_id)
        payload["watermark"] = None if final else "DRAFT — NOT FOR DISTRIBUTION"
        content = RENDERERS[fmt](payload)
        storage = Path(self.settings.local_storage_dir) / "reports" / str(report.id)
        storage.mkdir(parents=True, exist_ok=True)
        version_no = max([v.version for v in report.versions] or [0]) + 1
        file_name = f"{report.id}_v{version_no}{'_final' if final else '_draft'}.{fmt}"
        path = storage / file_name
        path.write_bytes(content)
        rv = ReportVersion(
            tenant_id=self.principal.tenant_id,
            report_id=report.id,
            version=version_no,
            format=fmt,
            storage_key=str(path),
            file_hash=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            generated_by=self.principal.user_id,
            is_final=final,
        )
        self.db.add(rv)
        self.db.flush()
        audit.record(
            self.db,
            tenant_id=self.principal.tenant_id,
            user_id=self.principal.user_id,
            action="report.generate_final" if final else "report.generate_draft_file",
            object_type="report_version",
            object_id=rv.id,
            new_value={"format": fmt, "hash": rv.file_hash, "final": final},
        )
        return rv
