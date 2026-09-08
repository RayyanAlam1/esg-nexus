from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DB, Page, User, get_entity, get_metric, get_org, get_period, paginate, serialize
from app.core import audit
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.security import require
from app.models.esg import MetricDefinition, MetricValue
from app.models.evidence import EVIDENCE_KINDS, Evidence, EvidenceLink
from app.models.governance import Issue
from app.models.organization import Entity, ReportingPeriod

router = APIRouter(prefix="/evidence", tags=["evidence"])


class EvidenceIn(BaseModel):
    code: str
    title: str
    kind: str
    source: str | None = None
    document_ref: str | None = None
    page_from: int | None = None
    page_to: int | None = None
    printed_page: str | None = None
    excerpt: str | None = None
    evidence_date: date | None = None
    entity_code: str | None = None
    period_code: str | None = None
    confidence: float | None = None
    metric_codes: list[str] = []


class LinkIn(BaseModel):
    metric_code: str
    entity_code: str | None = None
    period_code: str | None = None
    relation: str = "supports"
    note: str | None = None


class VerifyIn(BaseModel):
    status: str  # verified|rejected|unverified
    comment: str | None = None
    confidence: float | None = None


@router.get("/kinds")
def kinds():
    return EVIDENCE_KINDS


@router.get("")
def list_evidence(principal: User, db: DB, page: Page = Depends(), kind: str | None = None, status: str | None = None, q: str | None = None, metric: str | None = None):
    stmt = select(Evidence).where(Evidence.tenant_id == principal.tenant_id)
    if kind:
        stmt = stmt.where(Evidence.kind == kind)
    if status:
        stmt = stmt.where(Evidence.verification_status == status)
    if q:
        stmt = stmt.where(Evidence.title.ilike(f"%{q}%") | Evidence.code.ilike(f"%{q}%") | Evidence.excerpt.ilike(f"%{q}%"))
    if metric:
        m = get_metric(db, principal, metric)
        stmt = stmt.join(EvidenceLink, EvidenceLink.evidence_id == Evidence.id).where(EvidenceLink.metric_id == m.id).distinct()
    result = paginate(db, stmt.order_by(Evidence.code), page, Evidence)
    for item in result["items"]:
        item["excerpt"] = (item.get("excerpt") or "")[:300]
        item["link_count"] = db.execute(select(func.count(EvidenceLink.id)).where(EvidenceLink.evidence_id == item["id"])).scalar()
    return result


@router.get("/gaps")
def gaps(principal: User, db: DB, period: str | None = None, org_id: int | None = None):
    """Evidence gaps: evidence-required metrics with values but no evidence, plus open evidence issues."""
    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    entity_ids = [e.id for e in db.execute(select(Entity).where(Entity.organization_id == org.id)).scalars().all()]
    values = db.execute(select(MetricValue).where(MetricValue.period_id == p.id, MetricValue.entity_id.in_(entity_ids))).scalars().all()
    out, covered, required = [], 0, 0
    for mv in values:
        m = db.get(MetricDefinition, mv.metric_id)
        if not m.evidence_required or (mv.value_numeric is None and not mv.value_text):
            continue
        required += 1
        from app.engines.evidence_resolution import evidence_codes

        n = len(evidence_codes(db, m, db.get(Entity, mv.entity_id), p, mv))
        if n:
            covered += 1
        else:
            out.append(
                {
                    "metric_code": m.code,
                    "metric_name": m.name,
                    "entity": db.get(Entity, mv.entity_id).code,
                    "period": p.code,
                    "is_kpi": m.is_kpi,
                    "pillar": m.pillar,
                    "severity": "HIGH" if m.is_kpi else "MEDIUM",
                }
            )
    unverified = db.execute(select(func.count(Evidence.id)).where(Evidence.tenant_id == principal.tenant_id, Evidence.verification_status == "unverified")).scalar()
    issues = db.execute(select(Issue).where(Issue.tenant_id == principal.tenant_id, Issue.category == "evidence_gap", Issue.status.in_(["open", "acknowledged"]))).scalars().all()
    return {
        "period": p.code,
        "required": required,
        "covered": covered,
        "coverage_pct": round(covered / required * 100, 1) if required else 0,
        "gaps": out,
        "unverified_evidence": unverified,
        "open_issues": serialize(issues),
    }


@router.get("/{code}")
def evidence_detail(code: str, principal: User, db: DB):
    ev = db.execute(select(Evidence).where(Evidence.tenant_id == principal.tenant_id, Evidence.code == code)).scalars().first()
    if ev is None:
        raise NotFoundError("Evidence not found")
    links = []
    for link in ev.links:
        m = db.get(MetricDefinition, link.metric_id) if link.metric_id else None
        mv = db.get(MetricValue, link.metric_value_id) if link.metric_value_id else None
        links.append(
            {
                "id": link.id,
                "metric_code": m.code if m else None,
                "metric_name": m.name if m else None,
                "entity": db.get(Entity, mv.entity_id).code if mv else None,
                "period": db.get(ReportingPeriod, mv.period_id).code if mv else None,
                "value": mv.value_numeric if mv else None,
                "relation": link.relation,
                "requirement_id": link.requirement_id,
            }
        )
    return {**serialize(ev), "links": links}


@router.post("", dependencies=[Depends(require("evidence.write"))])
def create_evidence(body: EvidenceIn, principal: User, db: DB):
    org = get_org(db, principal)
    ev = Evidence(tenant_id=principal.tenant_id, owner_id=principal.user_id, **body.model_dump(exclude={"entity_code", "period_code", "metric_codes"}))
    if body.entity_code:
        ev.entity_id = get_entity(db, principal, org, body.entity_code).id
    if body.period_code:
        ev.period_id = get_period(db, org, body.period_code).id
    db.add(ev)
    db.flush()
    for mc in body.metric_codes:
        db.add(EvidenceLink(evidence_id=ev.id, metric_id=get_metric(db, principal, mc).id))
    audit.record(
        db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="evidence.upload", object_type="evidence", object_id=ev.code, new_value=body.model_dump(mode="json")
    )
    db.commit()
    return serialize(ev)


@router.post("/upload", dependencies=[Depends(require("evidence.write"))])
async def upload_evidence(
    principal: User,
    db: DB,
    file: UploadFile = File(...),
    code: str = Form(...),
    title: str = Form(...),
    kind: str = Form("pdf"),
    metric_code: str | None = Form(None),
    entity_code: str | None = Form(None),
    period_code: str | None = Form(None),
):
    from app.ai import guardrails

    g = guardrails.check_input("", file_name=file.filename or "")
    if g.blocked:
        from app.core.errors import GuardrailError

        raise GuardrailError("File rejected", details=g.findings)
    data = await file.read()
    settings = get_settings()
    # The storage key is generated server-side and partitioned per tenant: `code` and `filename`
    # are client-controlled and must never reach the filesystem path.
    folder = settings.local_storage_dir / "evidence" / str(principal.tenant_id)
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    original_name = Path(file.filename or "").name  # basename only: never a path, never displayed as one
    suffix = Path(original_name).suffix.lower()
    if suffix and (len(suffix) > 12 or not suffix[1:].isalnum()):
        suffix = ""
    path = folder / f"{uuid4().hex}{suffix}"
    path.write_bytes(data)
    org = get_org(db, principal)
    ev = Evidence(
        tenant_id=principal.tenant_id,
        code=code,
        title=title,
        kind=kind,
        document_ref=original_name or None,
        file_hash=digest,
        storage_key=str(path),
        owner_id=principal.user_id,
        evidence_date=date.today(),
        verification_status="unverified",
    )
    if entity_code:
        ev.entity_id = get_entity(db, principal, org, entity_code).id
    if period_code:
        ev.period_id = get_period(db, org, period_code).id
    db.add(ev)
    db.flush()
    if metric_code:
        m = get_metric(db, principal, metric_code)
        mv = None
        if entity_code and period_code:
            mv = (
                db.execute(select(MetricValue).where(MetricValue.metric_id == m.id, MetricValue.entity_id == ev.entity_id, MetricValue.period_id == ev.period_id)).scalars().first()
            )
        db.add(EvidenceLink(evidence_id=ev.id, metric_id=m.id, metric_value_id=mv.id if mv else None))
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="evidence.upload",
        object_type="evidence",
        object_id=ev.code,
        new_value={"file": file.filename, "hash": digest, "size": len(data)},
    )
    db.commit()
    return serialize(ev)


@router.post("/{code}/link", dependencies=[Depends(require("evidence.write"))])
def link(code: str, body: LinkIn, principal: User, db: DB):
    ev = db.execute(select(Evidence).where(Evidence.tenant_id == principal.tenant_id, Evidence.code == code)).scalars().first()
    if ev is None:
        raise NotFoundError("Evidence not found")
    org = get_org(db, principal)
    m = get_metric(db, principal, body.metric_code)
    mv = None
    if body.entity_code or body.period_code:
        e = get_entity(db, principal, org, body.entity_code)
        p = get_period(db, org, body.period_code)
        mv = db.execute(select(MetricValue).where(MetricValue.metric_id == m.id, MetricValue.entity_id == e.id, MetricValue.period_id == p.id)).scalars().first()
    link = EvidenceLink(evidence_id=ev.id, metric_id=m.id, metric_value_id=mv.id if mv else None, relation=body.relation, note=body.note)
    db.add(link)
    db.flush()
    audit.record(db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="evidence.link", object_type="evidence", object_id=ev.code, new_value=body.model_dump())
    if mv is not None:
        from app.engines import data_quality
        from app.services.governance_service import run_metric_rules

        data_quality.assess(db, principal.tenant_id, m, db.get(Entity, mv.entity_id), db.get(ReportingPeriod, mv.period_id))
        run_metric_rules(db, principal.tenant_id, org.id, db.get(ReportingPeriod, mv.period_id))
    db.commit()
    return serialize(link)


@router.post("/{code}/verify", dependencies=[Depends(require("evidence.verify"))])
def verify(code: str, body: VerifyIn, principal: User, db: DB):
    ev = db.execute(select(Evidence).where(Evidence.tenant_id == principal.tenant_id, Evidence.code == code)).scalars().first()
    if ev is None:
        raise NotFoundError("Evidence not found")
    old = ev.verification_status
    ev.verification_status = body.status
    ev.verified_by = principal.user_id
    if body.confidence is not None:
        ev.confidence = body.confidence
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="evidence.verify",
        object_type="evidence",
        object_id=ev.code,
        old_value={"status": old},
        new_value={"status": body.status},
        reason=body.comment,
    )
    db.commit()
    return serialize(ev)
