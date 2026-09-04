from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, User, get_metric, get_org, get_period, serialize
from app.core import audit
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.security import require
from app.engines import frameworks as fw_engine
from app.models.frameworks import Framework, FrameworkMapping, FrameworkVersion, OrganizationFramework, Requirement

router = APIRouter(prefix="/frameworks", tags=["standards"])


class MappingIn(BaseModel):
    requirement_code: str
    metric_code: str | None = None
    mapping_type: str = "direct"
    rationale: str | None = None
    omission_reason: str | None = None
    confidence: float | None = None


class SelectIn(BaseModel):
    framework_codes: list[str]
    period_code: str
    applicable_scope: dict | None = None


@router.get("")
def list_frameworks(principal: User, db: DB):
    out = []
    for fw in db.execute(select(Framework).order_by(Framework.code)).scalars().all():
        fv = fw_engine.current_version(db, fw.code)
        out.append(
            {
                **serialize(fw),
                "current_version": fv.version if fv else None,
                "effective_date": fv.effective_date.isoformat() if fv and fv.effective_date else None,
                "requirement_count": len(fv.requirements) if fv else 0,
                "versions": [v.version for v in fw.versions],
            }
        )
    return out


@router.get("/selected")
def selected(principal: User, db: DB, period: str | None = None, org_id: int | None = None):
    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    rows = db.execute(select(OrganizationFramework).where(OrganizationFramework.organization_id == org.id, OrganizationFramework.period_id == p.id)).scalars().all()
    out = []
    for r in rows:
        fv = db.get(FrameworkVersion, r.framework_version_id)
        out.append({**serialize(r), "framework_code": fv.framework.code, "framework_name": fv.framework.name, "version": fv.version})
    return {"period": p.code, "frameworks": out}


@router.post("/select", dependencies=[Depends(require("framework.manage"))])
def select_frameworks(body: SelectIn, principal: User, db: DB):
    org = get_org(db, principal)
    p = get_period(db, org, body.period_code)
    for code in body.framework_codes:
        fv = fw_engine.current_version(db, code)
        if fv is None:
            raise NotFoundError(f"Framework {code} not found")
        exists = (
            db.execute(
                select(OrganizationFramework).where(
                    OrganizationFramework.organization_id == org.id, OrganizationFramework.framework_version_id == fv.id, OrganizationFramework.period_id == p.id
                )
            )
            .scalars()
            .first()
        )
        if exists is None:
            db.add(
                OrganizationFramework(
                    tenant_id=principal.tenant_id,
                    organization_id=org.id,
                    framework_version_id=fv.id,
                    period_id=p.id,
                    applicable_scope=body.applicable_scope,
                    status="active",
                    is_primary=code in ("WEF_SCM", "UNGC", "UN_SDG"),
                )
            )
        else:
            exists.status = "active"
    audit.record(db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="framework.select", object_type="organization", object_id=org.id, new_value=body.model_dump())
    db.commit()
    return {"selected": body.framework_codes, "period": p.code}


@router.post("/reload", dependencies=[Depends(require("framework.manage"))])
def reload(principal: User, db: DB):
    codes = fw_engine.load_from_yaml(db, get_settings().frameworks_dir)
    audit.record(db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="framework.reload", object_type="framework", new_value={"codes": codes})
    db.commit()
    return {"loaded": codes}


@router.get("/{code}/requirements")
def requirements(code: str, principal: User, db: DB):
    fv = fw_engine.current_version(db, code)
    if fv is None:
        raise NotFoundError("Framework not found")
    return {"framework": serialize(fv.framework), "version": fv.version, "requirements": serialize(fv.requirements)}


@router.get("/{code}/coverage")
def coverage(code: str, principal: User, db: DB, period: str | None = None, org_id: int | None = None):
    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    return fw_engine.coverage(db, principal.tenant_id, org.id, p, code)


@router.get("/requirements/{req_code}")
def requirement(req_code: str, principal: User, db: DB, period: str | None = None, org_id: int | None = None):
    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    req = db.execute(select(Requirement).where(Requirement.code == req_code)).scalars().first()
    if req is None:
        raise NotFoundError("Requirement not found")
    status = fw_engine.requirement_status(db, principal.tenant_id, org.id, p, req)
    mappings = db.execute(select(FrameworkMapping).where(FrameworkMapping.tenant_id == principal.tenant_id, FrameworkMapping.requirement_id == req.id)).scalars().all()
    return {**status, "framework": req.framework_version.framework.code, "mappings": serialize(mappings), "period": p.code}


@router.post("/mappings", dependencies=[Depends(require("framework.manage"))])
def create_mapping(body: MappingIn, principal: User, db: DB):
    req = db.execute(select(Requirement).where(Requirement.code == body.requirement_code)).scalars().first()
    if req is None:
        raise NotFoundError("Requirement not found")
    metric = get_metric(db, principal, body.metric_code) if body.metric_code else None
    fm = FrameworkMapping(
        tenant_id=principal.tenant_id,
        requirement_id=req.id,
        metric_id=metric.id if metric else None,
        mapping_type=body.mapping_type,
        rationale=body.rationale,
        omission_reason=body.omission_reason,
        confidence=body.confidence,
        status="approved",
        created_by=principal.user_id,
    )
    db.add(fm)
    db.flush()
    audit.record(
        db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="framework.map", object_type="framework_mapping", object_id=fm.id, new_value=body.model_dump()
    )
    db.commit()
    return serialize(fm)


@router.get("/mappings/all")
def all_mappings(principal: User, db: DB):
    rows = db.execute(select(FrameworkMapping).where(FrameworkMapping.tenant_id == principal.tenant_id)).scalars().all()
    out = []
    for r in rows:
        req = db.get(Requirement, r.requirement_id)
        out.append({**serialize(r), "requirement_code": req.code, "requirement_title": req.title, "metric_code": get_metric_code(db, r.metric_id)})
    return out


def get_metric_code(db, metric_id):
    from app.models.esg import MetricDefinition

    m = db.get(MetricDefinition, metric_id) if metric_id else None
    return m.code if m else None


@router.post("/gap-analysis", dependencies=[Depends(require("ai.run"))])
def gap_analysis(principal: User, db: DB, framework: str = "WEF_SCM", period: str | None = None):
    from app.ai.agents import registry

    agent = registry.get("standards_mapping_agent")(db, principal)
    res = agent.run("gap_analysis", {"framework_code": framework, "period_code": period or "", "question": f"Which {framework} requirements are incomplete?"})
    db.commit()
    return res.as_dict()
