"""Framework engine: applicable requirements, coverage, gaps and alignment.

Frameworks are loaded from YAML configuration (`frameworks/*.yaml`) into the registry tables; this
module computes status per requirement for an organisation + period.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.esg import MetricDefinition, MetricValue
from app.models.frameworks import Framework, FrameworkMapping, FrameworkVersion, Requirement
from app.models.organization import Entity, ReportingPeriod
from app.models.reporting import Report, ReportSection


def load_from_yaml(db: Session, frameworks_dir: Path) -> list[str]:
    """Idempotently load every framework YAML into the registry. Returns loaded framework codes."""
    loaded: list[str] = []
    for path in sorted(Path(frameworks_dir).glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        fw_data = data["framework"]
        fw = db.execute(select(Framework).where(Framework.code == fw_data["code"])).scalars().first()
        if fw is None:
            fw = Framework(code=fw_data["code"])
            db.add(fw)
        fw.name = fw_data["name"]
        fw.publisher = fw_data.get("publisher")
        fw.description = fw_data.get("description")
        fw.jurisdiction = fw_data.get("jurisdiction")
        fw.industry = fw_data.get("industry")
        fw.is_custom = bool(fw_data.get("is_custom", False))
        db.flush()
        ver_data = data["version"]
        fv = db.execute(select(FrameworkVersion).where(FrameworkVersion.framework_id == fw.id, FrameworkVersion.version == str(ver_data["version"]))).scalars().first()
        if fv is None:
            fv = FrameworkVersion(framework_id=fw.id, version=str(ver_data["version"]))
            db.add(fv)
        fv.effective_date = ver_data.get("effective_date")
        fv.status = ver_data.get("status", "current")
        fv.source_url = ver_data.get("source_url")
        fv.notes = ver_data.get("notes")
        db.flush()
        existing = {r.code: r for r in db.execute(select(Requirement).where(Requirement.framework_version_id == fv.id)).scalars().all()}
        for order, req in enumerate(data.get("requirements", []), start=1):
            r = existing.get(req["code"])
            if r is None:
                r = Requirement(framework_version_id=fv.id, code=req["code"], title=req["title"])
                db.add(r)
            r.title = req["title"]
            r.description = req.get("description")
            r.pillar = req.get("pillar")
            r.theme = req.get("theme")
            r.disclosure_type = req.get("disclosure_type", "both")
            r.evidence_required = bool(req.get("evidence_required", True))
            r.is_core = bool(req.get("is_core", True))
            r.applicability = req.get("applicability")
            r.metric_codes = req.get("metrics", [])
            r.guidance = req.get("guidance")
            r.sort_order = order
            db.flush()
            if req.get("parent"):
                parent = (
                    existing.get(req["parent"])
                    or db.execute(select(Requirement).where(Requirement.framework_version_id == fv.id, Requirement.code == req["parent"])).scalars().first()
                )
                r.parent_id = parent.id if parent else None
            existing[r.code] = r
        loaded.append(fw.code)
    db.flush()
    return loaded


def current_version(db: Session, framework_code: str) -> FrameworkVersion | None:
    fw = db.execute(select(Framework).where(Framework.code == framework_code)).scalars().first()
    if fw is None:
        return None
    return (
        db.execute(select(FrameworkVersion).where(FrameworkVersion.framework_id == fw.id).order_by(FrameworkVersion.status == "current", FrameworkVersion.version.desc()))
        .scalars()
        .first()
    )


def requirement_status(db: Session, tenant_id: int, organization_id: int, period: ReportingPeriod, req: Requirement, *, group_entity: Entity | None = None) -> dict:
    """Status of one requirement: complete | partial | missing | omitted | narrative_only."""
    entity_ids = [e.id for e in db.execute(select(Entity).where(Entity.organization_id == organization_id)).scalars().all()]
    mappings = (
        db.execute(select(FrameworkMapping).where(FrameworkMapping.tenant_id == tenant_id, FrameworkMapping.requirement_id == req.id, FrameworkMapping.status == "approved"))
        .scalars()
        .all()
    )
    omitted = next((m for m in mappings if m.mapping_type == "omitted"), None)
    metric_codes = list(req.metric_codes or [])
    for m in mappings:
        if m.metric_id:
            md = db.get(MetricDefinition, m.metric_id)
            if md and md.code not in metric_codes:
                metric_codes.append(md.code)
    metrics = db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == tenant_id, MetricDefinition.code.in_(metric_codes))).scalars().all() if metric_codes else []
    metric_states = []
    for md in metrics:
        mvs = (
            db.execute(select(MetricValue).where(MetricValue.metric_id == md.id, MetricValue.period_id == period.id, MetricValue.entity_id.in_(entity_ids))).scalars().all()
            if entity_ids
            else []
        )
        has_value = any(mv.value_numeric is not None or mv.value_text for mv in mvs)
        from app.engines.evidence_resolution import evidence_codes

        has_evidence = False
        for mv in mvs:
            if evidence_codes(db, md, db.get(Entity, mv.entity_id), period, mv):
                has_evidence = True
                break
        metric_states.append({"code": md.code, "name": md.name, "has_value": has_value, "has_evidence": has_evidence, "kind": md.kind, "unit": md.unit})

    # narrative coverage: any approved/drafted report section referencing this requirement
    narrative = False
    sec = db.execute(select(ReportSection).join(Report, Report.id == ReportSection.report_id).where(Report.tenant_id == tenant_id, Report.period_id == period.id)).scalars().all()
    for s in sec:
        if req.code in (s.requirement_codes or []) and (s.content_md or "").strip():
            narrative = True
            break

    if omitted:
        status = "omitted"
    elif req.disclosure_type == "narrative":
        status = "complete" if narrative else ("partial" if metric_states and any(m["has_value"] for m in metric_states) else "missing")
    else:
        if not metric_states:
            status = "complete" if narrative and req.disclosure_type == "both" and not metric_codes else "missing"
        else:
            n_val = len([m for m in metric_states if m["has_value"]])
            status = "complete" if n_val == len(metric_states) else ("partial" if n_val else "missing")
    evidence_gap = req.evidence_required and any(m["has_value"] and not m["has_evidence"] for m in metric_states)
    metric_gap = any(not m["has_value"] for m in metric_states) or (not metric_states and req.disclosure_type == "quantitative")
    narrative_gap = req.disclosure_type in ("narrative", "both") and not narrative
    return {
        "code": req.code,
        "title": req.title,
        "pillar": req.pillar,
        "theme": req.theme,
        "disclosure_type": req.disclosure_type,
        "is_core": req.is_core,
        "status": status,
        "metrics": metric_states,
        "evidence_gap": bool(evidence_gap),
        "metric_gap": bool(metric_gap),
        "narrative_gap": bool(narrative_gap),
        "omission_reason": omitted.omission_reason if omitted else None,
        "description": req.description,
        "guidance": req.guidance,
    }


def coverage(db: Session, tenant_id: int, organization_id: int, period: ReportingPeriod, framework_code: str) -> dict:
    fv = current_version(db, framework_code)
    if fv is None:
        return {"framework": framework_code, "error": "unknown framework", "alignment_pct": 0.0, "requirements": []}
    reqs = db.execute(select(Requirement).where(Requirement.framework_version_id == fv.id).order_by(Requirement.sort_order)).scalars().all()
    statuses = [requirement_status(db, tenant_id, organization_id, period, r) for r in reqs]
    leaf = [s for s, r in zip(statuses, reqs, strict=False) if not any(x.parent_id == r.id for x in reqs)]
    applicable = [s for s in leaf if s["status"] != "omitted"]
    complete = [s for s in applicable if s["status"] == "complete"]
    partial = [s for s in applicable if s["status"] == "partial"]
    missing = [s for s in applicable if s["status"] == "missing"]
    score = (len(complete) + 0.5 * len(partial)) / len(applicable) * 100 if applicable else 0.0
    return {
        "framework": framework_code,
        "framework_name": fv.framework.name,
        "version": fv.version,
        "alignment_pct": round(score, 1),
        "applicable": len(applicable),
        "completed": len(complete),
        "partial": len(partial),
        "missing": len(missing),
        "omitted": len([s for s in leaf if s["status"] == "omitted"]),
        "evidence_gaps": len([s for s in applicable if s["evidence_gap"]]),
        "metric_gaps": len([s for s in applicable if s["metric_gap"]]),
        "narrative_gaps": len([s for s in applicable if s["narrative_gap"]]),
        "requirements": statuses,
        "disclaimer": "Framework Alignment is an internal readiness indicator, not a compliance certification. Final regulatory interpretation may require qualified professionals.",
    }
