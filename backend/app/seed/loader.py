"""Reference-data seeder: loads the ECORP 2023 dataset (YAML) into the database.

Idempotent — safe to run on every start-up. Order: tenant/users → organisation → taxonomy → frameworks →
evidence → metrics & values → data sources → targets → materiality → governance → knowledge base → agents →
report templates → engines (calculations, quality, rules).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import ROLES, hash_password
from app.engines import data_quality, metric_engine
from app.engines import frameworks as fw_engine
from app.models import (
    Agent,
    CalculationVersion,
    Dataset,
    DatasetVersion,
    DataSource,
    Entity,
    EsgSubtopic,
    EsgTopic,
    Evidence,
    EvidenceLink,
    Framework,
    FrameworkMapping,
    GovernancePolicy,
    GovernanceRule,
    KnowledgeChunk,
    KnowledgeDocument,
    MaterialityAssessment,
    MaterialityTopic,
    MetricDefinition,
    MetricValue,
    Organization,
    OrganizationFramework,
    ReportingPeriod,
    ReportTemplate,
    Requirement,
    Role,
    StakeholderInput,
    Target,
    Tenant,
    User,
    UserRole,
)
from app.services.governance_service import run_metric_rules

log = get_logger("seed")


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def printed_to_pdf_page(printed: int) -> int:
    return (printed + 5) // 2


class Seeder:
    def __init__(self, db: Session, seed_dir: Path | None = None):
        self.db = db
        self.settings = get_settings()
        self.seed_dir = Path(seed_dir or self.settings.seed_dir)
        self.pages: dict[int, dict] = {}
        self.tenant: Tenant | None = None
        self.org: Organization | None = None
        self.entities: dict[str, Entity] = {}
        self.periods: dict[str, ReportingPeriod] = {}
        self.metrics: dict[str, MetricDefinition] = {}
        self.evidence: dict[str, Evidence] = {}
        self.users: dict[str, User] = {}
        self.datasets_by_pillar: dict[str, DatasetVersion] = {}

    # ------------------------------------------------------------------ entry
    def run(self, *, recompute: bool = True) -> dict:
        db = self.db
        report = _yaml(self.seed_dir / "organization.yaml")
        self._load_pages()
        self._tenant_and_users(report)
        self._organization(report)
        self._topics()
        fw_codes = fw_engine.load_from_yaml(db, self.settings.frameworks_dir)
        self._source_document_evidence()
        self._metrics()
        self._data_sources()
        self._evidence_items()
        self._targets()
        self._materiality()
        self._governance()
        self._org_frameworks(fw_codes)
        self._mappings()
        self._knowledge_base()
        self._agents()
        self._templates()
        db.commit()
        stats = {"metrics": len(self.metrics), "entities": len(self.entities), "frameworks": fw_codes, "evidence": len(self.evidence)}
        if recompute:
            stats.update(self.recompute())
        log.info("seed complete", **{k: v for k, v in stats.items() if not isinstance(v, list)})
        return stats

    def recompute(self) -> dict:
        db = self.db
        out: dict = {}
        for code in ("FY2022", "FY2023"):
            period = self.periods[code]
            calcs = metric_engine.recalculate_all(db, self.tenant.id, self.org.id, period)
            out[f"calculations_{code}"] = len([c for c in calcs if c.status == "ok"])
            db.commit()
            q = data_quality.assess_all(db, self.tenant.id, self.org.id, period)
            out[f"quality_{code}"] = round(sum(r.overall for r in q) / len(q), 1) if q else 0
            db.commit()
            g = run_metric_rules(db, self.tenant.id, self.org.id, period)
            out[f"issues_{code}"] = g["issues_triggered"]
            db.commit()
        return out

    # ------------------------------------------------------------------ helpers
    def _get_or_create(self, model, defaults: dict | None = None, **filters):
        obj = self.db.execute(select(model).filter_by(**filters)).scalars().first()
        if obj is None:
            obj = model(**filters, **(defaults or {}))
            self.db.add(obj)
            self.db.flush()
            return obj, True
        for k, v in (defaults or {}).items():
            setattr(obj, k, v)
        return obj, False

    def _load_pages(self):
        path = self.seed_dir / "report_pages.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.pages = {p["pdf_page"]: p for p in data["pages"]}
            self.doc_meta = {k: v for k, v in data.items() if k != "pages"}
        else:
            self.doc_meta = {"document": "ECORP-Sustainability-Report-01-07-24.pdf", "sha256": None}

    # ------------------------------------------------------------------ tenant, roles, users
    def _tenant_and_users(self, data: dict):
        t = data["tenant"]
        self.tenant, _ = self._get_or_create(Tenant, {"name": t["name"], "deployment_model": t.get("deployment_model", "saas")}, slug=t["slug"])
        for r in ROLES:
            self._get_or_create(Role, {"description": r.replace("_", " ").title()}, name=r)
        for u in data.get("users", []):
            user, _created = self._get_or_create(
                User, {"full_name": u["name"], "password_hash": hash_password(u["password"]), "is_active": True}, tenant_id=self.tenant.id, email=u["email"]
            )
            self.users[u["email"]] = user
            self._pending_user_roles = getattr(self, "_pending_user_roles", [])
            self._pending_user_roles.append((user, u))

    def _organization(self, data: dict):
        o = data["organization"]
        self.org, _ = self._get_or_create(
            Organization,
            {
                k: o.get(k)
                for k in ("name", "legal_name", "legal_form", "headquarters", "country", "stock_ticker", "sector", "description", "reporting_boundary", "website", "contact")
            },
            tenant_id=self.tenant.id,
            code=o["code"],
        )
        for p in data["periods"]:
            period, _ = self._get_or_create(
                ReportingPeriod,
                {
                    "label": p["label"],
                    "start_date": p["start"],
                    "end_date": p["end"],
                    "status": p.get("status", "open"),
                    "granularity": "year",
                    "is_baseline": bool(p.get("is_baseline")),
                },
                tenant_id=self.tenant.id,
                organization_id=self.org.id,
                code=p["code"],
            )
            self.periods[p["code"]] = period
        # two-pass for parents
        for e in data["entities"]:
            ent, _ = self._get_or_create(
                Entity,
                {
                    "name": e["name"],
                    "kind": e.get("kind", "subsidiary"),
                    "ownership_pct": e.get("ownership_pct"),
                    "consolidation_method": e.get("consolidation_method", "full"),
                    "in_reporting_boundary": bool(e.get("in_reporting_boundary", True)),
                    "country": e.get("country"),
                    "region": e.get("region"),
                    "location": e.get("location"),
                    "sector": e.get("sector"),
                    "description": e.get("description"),
                    "attributes": e.get("attributes"),
                    "organization_id": self.org.id,
                },
                tenant_id=self.tenant.id,
                code=e["code"],
            )
            self.entities[e["code"]] = ent
        for e in data["entities"]:
            if e.get("parent"):
                self.entities[e["code"]].parent_id = self.entities[e["parent"]].id
        self.db.flush()
        # role assignments (need entities for scoping)
        for user, u in getattr(self, "_pending_user_roles", []):
            for role in u.get("roles", []):
                exists = self.db.execute(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_name == role)).scalars().first()
                if exists is None:
                    self.db.add(UserRole(user_id=user.id, role_name=role, organization_id=self.org.id, entity_id=self.entities[u["entity"]].id if u.get("entity") else None))
        self.db.flush()

    def _topics(self):
        data = _yaml(self.seed_dir / "topics.yaml")
        for i, t in enumerate(data["topics"]):
            topic, _ = self._get_or_create(EsgTopic, {"name": t["name"], "pillar": t["pillar"], "sort_order": i}, tenant_id=self.tenant.id, code=t["code"])
            for s in t.get("subtopics", []):
                self._get_or_create(EsgSubtopic, {"name": s.replace("_", " ").title()}, topic_id=topic.id, code=s)

    # ------------------------------------------------------------------ evidence
    def _source_document_evidence(self):
        ev = _yaml(self.seed_dir / "evidence.yaml")
        self.source_doc = ev["source_document"]

    def page_evidence(self, ref: str) -> Evidence:
        """`P80` → Evidence for printed page 80 of the report (created on first use)."""
        code = f"EV-RPT23-{ref}"
        if code in self.evidence:
            return self.evidence[code]
        printed = int(ref[1:])
        pdf_page = printed_to_pdf_page(printed)
        page = self.pages.get(pdf_page, {})
        text = (page.get("text") or "").strip()
        excerpt = text[:1800] + ("…" if len(text) > 1800 else "")
        evidence, _ = self._get_or_create(
            Evidence,
            {
                "title": f"Sustainability Report 2023 — page {printed} (PDF p.{pdf_page})",
                "kind": "report_page",
                "source": "Engro Corporation Limited — published sustainability report",
                "document_ref": self.source_doc["file_name"],
                "page_from": pdf_page,
                "page_to": pdf_page,
                "printed_page": str(printed),
                "excerpt": excerpt or "Page is image-only; no extractable text.",
                "evidence_date": date(2024, 7, 1),
                "verification_status": self.source_doc.get("verification_status", "verified"),
                "confidence": self.source_doc.get("confidence", 0.9),
                "file_hash": self.source_doc.get("sha256"),
                "meta": {"document_code": self.source_doc["code"], "printed_pages_on_pdf_page": page.get("printed_pages")},
            },
            tenant_id=self.tenant.id,
            code=code,
        )
        self.evidence[code] = evidence
        return evidence

    def _evidence_items(self):
        ev = _yaml(self.seed_dir / "evidence.yaml")
        for item in ev.get("items", []):
            evidence, _ = self._get_or_create(
                Evidence,
                {
                    "title": item["title"],
                    "kind": item["kind"],
                    "source": item.get("source"),
                    "document_ref": item.get("document_ref"),
                    "page_from": item.get("page_from"),
                    "page_to": item.get("page_to"),
                    "printed_page": item.get("printed_page"),
                    "excerpt": item.get("excerpt"),
                    "evidence_date": item.get("evidence_date"),
                    "verification_status": item.get("verification_status", "unverified"),
                    "confidence": item.get("confidence"),
                },
                tenant_id=self.tenant.id,
                code=item["code"],
            )
            self.evidence[item["code"]] = evidence
            for mcode in item.get("links", []):
                metric = self.metrics.get(mcode)
                if metric is None:
                    continue
                exists = (
                    self.db.execute(
                        select(EvidenceLink).where(EvidenceLink.evidence_id == evidence.id, EvidenceLink.metric_id == metric.id, EvidenceLink.metric_value_id.is_(None))
                    )
                    .scalars()
                    .first()
                )
                if exists is None:
                    self.db.add(EvidenceLink(evidence_id=evidence.id, metric_id=metric.id, relation="supports"))
        self.db.flush()

    # ------------------------------------------------------------------ metrics
    def _metrics(self):
        topics = {t.code: t for t in self.db.execute(select(EsgTopic).where(EsgTopic.tenant_id == self.tenant.id)).scalars().all()}
        for path in sorted(self.seed_dir.glob("metrics_*.yaml")):
            data = _yaml(path)
            defaults = data.get("defaults", {})
            for m in data["metrics"]:
                topic = topics[m["topic"]]
                metric, _ = self._get_or_create(
                    MetricDefinition,
                    {
                        "name": m["name"],
                        "description": m.get("description"),
                        "pillar": topic.pillar,
                        "topic_code": m["topic"],
                        "subtopic_code": m.get("subtopic"),
                        "unit": m.get("unit"),
                        "frequency": m.get("frequency", "annual"),
                        "data_type": m.get("data_type", "decimal"),
                        "kind": m.get("kind", "raw"),
                        "calculation_method": m.get("method"),
                        "formula": m.get("formula"),
                        "required_inputs": m.get("inputs"),
                        "data_sources": m.get("sources"),
                        "evidence_required": bool(m.get("evidence_required", defaults.get("evidence_required", True))),
                        "evidence_requirements": m.get("evidence_requirements"),
                        "applicable_frameworks": m.get("frameworks", []),
                        "materiality_topic": m.get("materiality"),
                        "assurance_status": m.get("assurance", defaults.get("assurance", "not_assured")),
                        "validation_rules": m.get("validation"),
                        "aggregation": m.get("aggregation", "sum"),
                        "direction": m.get("direction"),
                        "tags": m.get("tags"),
                        "is_kpi": bool(m.get("is_kpi", False)),
                        "owner": m.get("owner"),
                    },
                    tenant_id=self.tenant.id,
                    code=m["code"],
                )
                self.metrics[m["code"]] = metric
                if m.get("formula"):
                    self._get_or_create(
                        CalculationVersion,
                        {"formula": m["formula"], "description": m.get("method") or m.get("description"), "is_current": True, "methodology_ref": "seed/ecorp_2023"},
                        tenant_id=self.tenant.id,
                        metric_id=metric.id,
                        version="1.0",
                    )
                status = m.get("status", defaults.get("status", "final"))
                source_type = m.get("source_type", "reported")
                evidence_refs = m.get("evidence", []) or []
                confidence = 0.75 if m.get("is_estimate") else 0.95
                for ecode, series in (m.get("values") or {}).items():
                    for pcode, val in series.items():
                        self._upsert_value(
                            metric,
                            ecode,
                            pcode,
                            value_numeric=float(val),
                            status=status,
                            source_type=source_type,
                            is_estimate=bool(m.get("is_estimate")),
                            confidence=confidence,
                            notes=m.get("notes"),
                            evidence_refs=evidence_refs,
                        )
                for ecode, series in (m.get("text_values") or {}).items():
                    for pcode, text in series.items():
                        self._upsert_value(
                            metric, ecode, pcode, value_text=text, status=status, source_type=source_type, confidence=0.9, notes=m.get("notes"), evidence_refs=evidence_refs
                        )
        self.db.flush()

    def _upsert_value(
        self,
        metric: MetricDefinition,
        ecode: str,
        pcode: str,
        *,
        value_numeric=None,
        value_text=None,
        status="final",
        source_type="reported",
        is_estimate=False,
        confidence=0.9,
        notes=None,
        evidence_refs=(),
    ):
        entity, period = self.entities[ecode], self.periods[pcode]
        mv = (
            self.db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == period.id)).scalars().first()
        )
        if mv is None:
            mv = MetricValue(tenant_id=self.tenant.id, metric_id=metric.id, entity_id=entity.id, period_id=period.id)
            self.db.add(mv)
        if value_numeric is not None:
            mv.value_numeric = value_numeric
        if value_text is not None:
            mv.value_text = value_text
        mv.unit, mv.status, mv.source_type, mv.is_estimate, mv.confidence, mv.notes = metric.unit, status, source_type, is_estimate, confidence, notes
        self.db.flush()
        for ref in evidence_refs:
            ev = self.page_evidence(ref)
            exists = self.db.execute(select(EvidenceLink).where(EvidenceLink.evidence_id == ev.id, EvidenceLink.metric_value_id == mv.id)).scalars().first()
            if exists is None:
                self.db.add(EvidenceLink(evidence_id=ev.id, metric_id=metric.id, metric_value_id=mv.id, relation="supports"))
        return mv

    # ------------------------------------------------------------------ data sources → lineage
    def _data_sources(self):
        data = _yaml(self.seed_dir / "data_sources.yaml")
        for s in data["sources"]:
            src, _ = self._get_or_create(
                DataSource,
                {
                    "name": s["name"],
                    "kind": s["kind"],
                    "system_name": s.get("system_name"),
                    "owner": s.get("owner"),
                    "description": s.get("description"),
                    "organization_id": self.org.id,
                },
                tenant_id=self.tenant.id,
                code=s["code"],
            )
            for d in s.get("datasets", []):
                ds, _ = self._get_or_create(
                    Dataset,
                    {"name": d["name"], "pillar": d.get("pillar"), "period_id": self.periods[d["period"]].id if d.get("period") else None, "source_id": src.id},
                    tenant_id=self.tenant.id,
                    code=d["code"],
                )
                dv, _ = self._get_or_create(
                    DatasetVersion,
                    {
                        "file_name": self.source_doc["file_name"],
                        "file_hash": self.source_doc.get("sha256"),
                        "status": "loaded",
                        "validation_result": {"valid": True, "method": "document extraction + analyst mapping"},
                        "transformation_history": [
                            {"step": "pdf_text_extraction", "tool": "pypdf"},
                            {"step": "table_reconstruction", "by": "analyst"},
                            {"step": "metric_mapping", "by": "ESG Data Agent + analyst confirmation"},
                        ],
                        "uploaded_by": self.users.get("analyst@ecorp.local").id if self.users.get("analyst@ecorp.local") else None,
                    },
                    tenant_id=self.tenant.id,
                    dataset_id=ds.id,
                    version=1,
                )
                if d.get("pillar"):
                    self.datasets_by_pillar[d["pillar"]] = dv
        # attach reported values to the pillar dataset version
        for metric in self.metrics.values():
            dv = self.datasets_by_pillar.get(metric.pillar)
            if dv is None:
                continue
            for mv in (
                self.db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.dataset_version_id.is_(None), MetricValue.source_type == "reported"))
                .scalars()
                .all()
            ):
                mv.dataset_version_id = dv.id
        for dv in set(self.datasets_by_pillar.values()):
            dv.row_count = self.db.execute(select(MetricValue).where(MetricValue.dataset_version_id == dv.id)).scalars().all().__len__()
        self.db.flush()

    # ------------------------------------------------------------------ targets, materiality, governance
    def _targets(self):
        data = _yaml(self.seed_dir / "targets.yaml")
        for t in data["targets"]:
            metric = self.metrics[t["metric"]]
            entity = self.entities[t["entity"]]
            existing = self.db.execute(select(Target).where(Target.metric_id == metric.id, Target.entity_id == entity.id)).scalars().first()
            if existing is None:
                existing = Target(tenant_id=self.tenant.id, metric_id=metric.id, entity_id=entity.id)
                self.db.add(existing)
            existing.baseline_value, existing.target_value, existing.direction = t.get("baseline_value"), t.get("target_value"), t.get("direction", "decrease")
            existing.kind, existing.target_year, existing.status, existing.description = (
                t.get("kind", "absolute"),
                t.get("target_year"),
                t.get("status", "active"),
                t.get("description"),
            )
            existing.source_evidence_code = f"EV-RPT23-{t['evidence']}" if t.get("evidence") else None
            existing.baseline_period_id = self.periods["FY2022"].id
        self.db.flush()

    def _materiality(self):
        data = _yaml(self.seed_dir / "materiality.yaml")
        a = data["assessment"]
        assessment, created = self._get_or_create(
            MaterialityAssessment,
            {
                "methodology": a.get("methodology"),
                "approach": a.get("approach", "impact"),
                "threshold": a.get("threshold", 3.0),
                "status": a.get("status", "draft"),
                "evidence_codes": [f"EV-RPT23-{p}" for p in a.get("evidence", [])],
            },
            tenant_id=self.tenant.id,
            organization_id=self.org.id,
            period_id=self.periods[a["period"]].id,
            name=a["name"],
        )
        for p in a.get("evidence", []):
            self.page_evidence(p)
        existing = {t.topic_code: t for t in assessment.topics}
        for t in data["topics"]:
            topic = existing.get(t["code"]) or MaterialityTopic(assessment_id=assessment.id, topic_code=t["code"], name=t["name"], pillar=t["pillar"])
            topic.name, topic.pillar = t["name"], t["pillar"]
            topic.impact_severity, topic.impact_likelihood = t.get("impact_severity"), t.get("impact_likelihood")
            topic.impact_score = round((t.get("impact_severity") or 0) * (t.get("impact_likelihood") or 0) / 5, 2)
            topic.financial_magnitude, topic.financial_likelihood = t.get("financial_magnitude"), t.get("financial_likelihood")
            topic.financial_score = round((t.get("financial_magnitude") or 0) * (t.get("financial_likelihood") or 0) / 5, 2)
            topic.stakeholder_priority, topic.is_material, topic.rationale = t.get("stakeholder_priority"), bool(t.get("is_material")), t.get("rationale")
            topic.related_metric_codes, topic.related_requirement_codes = t.get("metrics", []), t.get("requirements", [])
            topic.risks, topic.opportunities = t.get("risks", []), t.get("opportunities", [])
            topic.evidence_codes = ["EV-RPT23-P38"]
            if topic.id is None:
                self.db.add(topic)
        if created or not assessment.stakeholder_inputs:
            for s in data.get("stakeholder_inputs", []):
                self.db.add(
                    StakeholderInput(
                        assessment_id=assessment.id,
                        stakeholder_group=s["group"],
                        topic_code=s.get("topic"),
                        priority=s.get("priority"),
                        channel=s.get("channel"),
                        concern=s.get("concern"),
                    )
                )
        self.db.flush()

    def _governance(self):
        data = _yaml(self.seed_dir / "governance.yaml")
        for p in data.get("policies", []):
            self._get_or_create(
                GovernancePolicy,
                {
                    "name": p["name"],
                    "category": p.get("category"),
                    "owner": p.get("owner"),
                    "version": str(p.get("version", "1.0")),
                    "effective_date": p.get("effective_date"),
                    "description": p.get("description"),
                    "evidence_code": p.get("evidence"),
                    "status": "active",
                },
                tenant_id=self.tenant.id,
                code=p["code"],
            )
        for r in data.get("rules", []):
            self._get_or_create(
                GovernanceRule,
                {
                    "description": r["description"],
                    "severity": r.get("severity", "MEDIUM"),
                    "scope": r["scope"],
                    "condition": r["condition"],
                    "action": r["action"],
                    "message": r.get("message"),
                    "required_action": r.get("required_action"),
                    "owner": r.get("owner"),
                    "version": str(r.get("version", "1.0")),
                    "effective_date": r.get("effective_date") or date(2024, 1, 1),
                    "approval_status": "approved",
                    "is_active": True,
                    "policy_code": r.get("policy"),
                },
                tenant_id=self.tenant.id,
                code=r["code"],
            )
        self.db.flush()

    def _org_frameworks(self, codes: list[str]):
        primary = {"WEF_SCM", "UNGC", "UN_SDG"}
        for code in codes:
            fv = fw_engine.current_version(self.db, code)
            if fv is None:
                continue
            for pcode in ("FY2022", "FY2023"):
                self._get_or_create(
                    OrganizationFramework,
                    {
                        "status": "active" if code in primary else "assessment",
                        "is_primary": code in primary,
                        "applicable_scope": {"entities": [e for e, ent in self.entities.items() if ent.in_reporting_boundary]},
                    },
                    tenant_id=self.tenant.id,
                    organization_id=self.org.id,
                    framework_version_id=fv.id,
                    period_id=self.periods[pcode].id,
                )

    def _mappings(self):
        """Approved omissions recorded in the report's WEF index."""
        omissions = [
            (
                "WEF_SCM",
                "WEF.PEOPLE.WAGE_LEVEL",
                "SOC.COMP.CEO_PAY_RATIO",
                "CEO pay ratio omitted due to confidential data (WEF index, p.151). Entry-level wage ratio is reported (3x).",
            ),
        ]
        for fw_code, req_code, metric_code, reason in omissions:
            fv = fw_engine.current_version(self.db, fw_code)
            req = self.db.execute(select(Requirement).where(Requirement.framework_version_id == fv.id, Requirement.code == req_code)).scalars().first()
            metric = self.metrics.get(metric_code)
            if req is None or metric is None:
                continue
            exists = (
                self.db.execute(
                    select(FrameworkMapping).where(FrameworkMapping.tenant_id == self.tenant.id, FrameworkMapping.requirement_id == req.id, FrameworkMapping.metric_id == metric.id)
                )
                .scalars()
                .first()
            )
            if exists is None:
                # partial omission: the requirement stays 'partial' because the other metric is reported; record rationale on the mapping
                self.db.add(
                    FrameworkMapping(
                        tenant_id=self.tenant.id,
                        requirement_id=req.id,
                        metric_id=metric.id,
                        mapping_type="partial",
                        rationale=reason,
                        status="approved",
                        confidence=1.0,
                        omission_reason=reason,
                    )
                )
        self.db.flush()

    # ------------------------------------------------------------------ knowledge base (RAG)
    def _knowledge_base(self):
        # 1. the report, page by page
        doc, created = self._get_or_create(
            KnowledgeDocument,
            {
                "title": "Engro Corporation Sustainability Report 2023",
                "kind": "report",
                "version": "2023",
                "source_ref": self.source_doc["file_name"],
                "freshness_date": date(2024, 7, 1),
                "permissions": {"roles": ["*"]},
                "status": "approved",
                "meta": {"sha256": self.source_doc.get("sha256"), "pages": len(self.pages)},
            },
            tenant_id=self.tenant.id,
            code="KB-REPORT-2023",
        )
        if created or not doc.chunks:
            for pdf_page, page in sorted(self.pages.items()):
                text = (page.get("text") or "").strip()
                if len(text) < 40:
                    continue
                self.db.add(
                    KnowledgeChunk(
                        document_id=doc.id, chunk_index=pdf_page, text=text[:6000], meta={"pdf_page": pdf_page, "printed_pages": page.get("printed_pages"), "source": "report"}
                    )
                )
        # 2. metric definitions
        mdoc, created = self._get_or_create(
            KnowledgeDocument,
            {
                "title": "ESG Nexus metric definitions and methodologies",
                "kind": "metric_definition",
                "version": "1",
                "freshness_date": date.today(),
                "permissions": {"roles": ["*"]},
                "status": "approved",
            },
            tenant_id=self.tenant.id,
            code="KB-METRIC-DEFINITIONS",
        )
        if created or not mdoc.chunks:
            for i, m in enumerate(self.metrics.values()):
                text = f"{m.code} — {m.name}. Pillar: {m.pillar}; topic: {m.topic_code}; unit: {m.unit or 'n/a'}; kind: {m.kind}. {m.description or ''}"
                if m.formula:
                    text += f" Formula: {m.formula}. Method: {m.calculation_method or ''}"
                if m.applicable_frameworks:
                    text += f" Frameworks: {', '.join(m.applicable_frameworks)}."
                self.db.add(KnowledgeChunk(document_id=mdoc.id, chunk_index=i, text=text, meta={"metric_code": m.code, "source": "metric_definition"}))
        # 3. framework requirements
        for fw in self.db.execute(select(Framework)).scalars().all():
            fv = fw_engine.current_version(self.db, fw.code)
            fdoc, created = self._get_or_create(
                KnowledgeDocument,
                {
                    "title": f"{fw.name} — requirements ({fv.version})",
                    "kind": "framework",
                    "version": fv.version,
                    "source_ref": fv.source_url,
                    "freshness_date": fv.effective_date,
                    "permissions": {"roles": ["*"]},
                    "status": "approved",
                },
                tenant_id=self.tenant.id,
                code=f"KB-FW-{fw.code}",
            )
            if created or not fdoc.chunks:
                for i, r in enumerate(fv.requirements):
                    text = f"{r.code} — {r.title}. {r.description or ''} Disclosure type: {r.disclosure_type}. Metrics: {', '.join(r.metric_codes or [])}. {r.guidance or ''}"
                    self.db.add(KnowledgeChunk(document_id=fdoc.id, chunk_index=i, text=text, meta={"requirement_code": r.code, "framework": fw.code, "source": "framework"}))
        # 4. policies and governance rules (restricted to governance roles for demonstration of permission-aware RAG)
        pdoc, created = self._get_or_create(
            KnowledgeDocument,
            {
                "title": "Governance policies and rules",
                "kind": "policy",
                "version": "1",
                "freshness_date": date.today(),
                "permissions": {"roles": ["super_admin", "org_admin", "esg_manager", "reviewer", "auditor", "report_approver", "executive", "esg_analyst"]},
                "status": "approved",
            },
            tenant_id=self.tenant.id,
            code="KB-POLICIES",
        )
        if created or not pdoc.chunks:
            i = 0
            for p in self.db.execute(select(GovernancePolicy).where(GovernancePolicy.tenant_id == self.tenant.id)).scalars().all():
                self.db.add(
                    KnowledgeChunk(
                        document_id=pdoc.id,
                        chunk_index=i,
                        text=f"Policy {p.code} — {p.name} ({p.category}). Owner: {p.owner}. {p.description or ''}",
                        meta={"policy_code": p.code, "source": "policy"},
                    )
                )
                i += 1
            for r in self.db.execute(select(GovernanceRule).where(GovernanceRule.tenant_id == self.tenant.id)).scalars().all():
                self.db.add(
                    KnowledgeChunk(
                        document_id=pdoc.id,
                        chunk_index=i,
                        text=f"Governance rule {r.code} ({r.severity}, {r.action}): {r.description}. Condition: {r.condition}. Required action: {r.required_action or ''}",
                        meta={"rule_code": r.code, "source": "governance_rule"},
                    )
                )
                i += 1
        # 5. methodology
        mth, created = self._get_or_create(
            KnowledgeDocument,
            {"title": "Calculation methodologies", "kind": "methodology", "version": "1", "freshness_date": date.today(), "permissions": {"roles": ["*"]}, "status": "approved"},
            tenant_id=self.tenant.id,
            code="KB-METHODOLOGY",
        )
        if created or not mth.chunks:
            methods = [
                "TRIR (Total Recordable Incident Rate) = recordable injuries × 200,000 ÷ hours worked (OSHA basis, 100 full-time workers). For contractors the report includes fatalities in the numerator.",
                "LTIFR = lost-time injuries × 1,000,000 ÷ hours worked.",
                "Employee turnover rate = exits ÷ average (or year-end permanent) workforce × 100. The reference dataset uses year-end permanent employees, matching the report's 16% / 18%.",
                "GHG intensity = (Scope 1 + Scope 2) tCO2e ÷ consolidated revenue (PKR mn). Energy intensity = GJ ÷ revenue.",
                "Renewable energy percentage = renewable energy consumption ÷ total energy consumption × 100.",
                "Water balance check = withdrawn − consumed − discharged; a residual near zero confirms the balance closes.",
                "Consolidation: full (100%), proportional (ownership %), equity/excluded (0%). Group totals are the consolidated sum of entity values; printed totals are stored separately and reconciled.",
                "Data quality score = weighted blend of completeness 20%, accuracy 20%, consistency 15%, timeliness 10%, validity 15%, uniqueness 5%, traceability 15%.",
                "Report readiness = data completeness 18%, data quality 17%, evidence coverage 17%, framework alignment 16%, governance checks 12%, AI evaluation 8%, human approvals 12%; open issues reduce governance checks by severity (CRITICAL −4, HIGH −1.5, MEDIUM −0.6, LOW −0.2).",
            ]
            for i, t in enumerate(methods):
                self.db.add(KnowledgeChunk(document_id=mth.id, chunk_index=i, text=t, meta={"source": "methodology"}))
        self.db.flush()

    # ------------------------------------------------------------------ agents & templates
    def _agents(self):
        from app.ai.agents import registry as agent_registry

        for spec in agent_registry.specs():
            self._get_or_create(
                Agent,
                {
                    "name": spec.name,
                    "description": spec.description,
                    "responsibilities": spec.responsibilities,
                    "tools": spec.tools,
                    "expert_profile": spec.expert,
                    "version": spec.version,
                    "is_active": True,
                },
                code=spec.code,
            )

    def _templates(self):
        from app.reports.templates import load_templates

        for tpl in load_templates():
            self._get_or_create(ReportTemplate, {"name": tpl["name"], "description": tpl.get("description"), "sections": tpl["sections"]}, code=tpl["code"])


def seed_if_needed(db: Session) -> None:
    settings = get_settings()
    if not settings.auto_seed:
        return
    existing = db.execute(select(Tenant).where(Tenant.slug == "ecorp")).scalars().first()
    has_values = db.execute(select(MetricValue).limit(1)).scalars().first() is not None
    if existing is not None and has_values:
        return
    Seeder(db).run(recompute=True)
