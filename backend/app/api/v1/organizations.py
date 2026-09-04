from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, User, get_org, serialize
from app.core import audit
from app.core.security import require
from app.engines.consolidation import tree
from app.models.organization import Entity, Organization, ReportingPeriod

router = APIRouter(prefix="/organizations", tags=["organizations"])


class EntityIn(BaseModel):
    code: str
    name: str
    kind: str = "subsidiary"
    parent_code: str | None = None
    ownership_pct: float | None = None
    consolidation_method: str = "full"
    in_reporting_boundary: bool = True
    country: str | None = None
    region: str | None = None
    location: str | None = None
    sector: str | None = None
    description: str | None = None
    attributes: dict | None = None


class PeriodIn(BaseModel):
    code: str
    label: str
    start_date: date
    end_date: date
    granularity: str = "year"
    status: str = "open"


@router.get("")
def list_orgs(principal: User, db: DB):
    stmt = select(Organization).where(Organization.tenant_id == principal.tenant_id)
    if principal.organization_ids:
        stmt = stmt.where(Organization.id.in_(principal.organization_ids))
    return serialize(db.execute(stmt).scalars().all())


@router.get("/{org_id}")
def get_org_detail(org_id: int, principal: User, db: DB):
    org = get_org(db, principal, org_id)
    periods = db.execute(select(ReportingPeriod).where(ReportingPeriod.organization_id == org.id).order_by(ReportingPeriod.start_date)).scalars().all()
    return {**serialize(org), "periods": serialize(periods), "entities": tree(db, org.id)}


@router.get("/{org_id}/entities")
def entities(org_id: int, principal: User, db: DB, flat: bool = False):
    org = get_org(db, principal, org_id)
    if flat:
        return serialize(db.execute(select(Entity).where(Entity.organization_id == org.id).order_by(Entity.code)).scalars().all())
    return tree(db, org.id)


@router.post("/{org_id}/entities", dependencies=[Depends(require("admin"))])
def create_entity(org_id: int, body: EntityIn, principal: User, db: DB):
    org = get_org(db, principal, org_id)
    parent = db.execute(select(Entity).where(Entity.organization_id == org.id, Entity.code == body.parent_code)).scalars().first() if body.parent_code else None
    e = Entity(tenant_id=principal.tenant_id, organization_id=org.id, parent_id=parent.id if parent else None, **body.model_dump(exclude={"parent_code"}))
    db.add(e)
    db.flush()
    audit.record(db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="entity.create", object_type="entity", object_id=e.id, new_value=body.model_dump())
    db.commit()
    return serialize(e)


@router.get("/{org_id}/periods")
def periods(org_id: int, principal: User, db: DB):
    org = get_org(db, principal, org_id)
    return serialize(db.execute(select(ReportingPeriod).where(ReportingPeriod.organization_id == org.id).order_by(ReportingPeriod.start_date)).scalars().all())


@router.post("/{org_id}/periods", dependencies=[Depends(require("admin"))])
def create_period(org_id: int, body: PeriodIn, principal: User, db: DB):
    org = get_org(db, principal, org_id)
    p = ReportingPeriod(tenant_id=principal.tenant_id, organization_id=org.id, **body.model_dump())
    db.add(p)
    db.flush()
    audit.record(
        db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="period.create", object_type="reporting_period", object_id=p.id, new_value=body.model_dump(mode="json")
    )
    db.commit()
    return serialize(p)
