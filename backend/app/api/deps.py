"""Shared API dependencies and serialisation helpers."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import NotFoundError
from app.core.security import Principal, get_principal
from app.models.esg import MetricDefinition
from app.models.organization import Entity, Organization, ReportingPeriod

DB = Annotated[Session, Depends(get_db)]
User = Annotated[Principal, Depends(get_principal)]


class Page:
    def __init__(self, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), sort: str | None = Query(None), order: str = Query("asc")):
        self.limit, self.offset, self.sort, self.order = limit, offset, sort, order


def serialize(obj: Any, *, exclude: set[str] | None = None) -> Any:
    """SQLAlchemy model → dict (columns only)."""
    if obj is None:
        return None
    if isinstance(obj, list):
        return [serialize(o, exclude=exclude) for o in obj]
    if hasattr(obj, "__table__"):
        out = {}
        for col in obj.__table__.columns:
            if exclude and col.name in exclude:
                continue
            v = getattr(obj, col.name)
            out[col.name] = v.isoformat() if isinstance(v, (datetime, date)) else v
        return out
    return obj


def paginate(db: Session, stmt, page: Page, model=None):
    from sqlalchemy import func

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    if page.sort and model is not None and hasattr(model, page.sort):
        col = getattr(model, page.sort)
        stmt = stmt.order_by(col.desc() if page.order == "desc" else col.asc())
    items = db.execute(stmt.limit(page.limit).offset(page.offset)).scalars().all()
    return {"items": serialize(items), "total": total, "limit": page.limit, "offset": page.offset}


def get_org(db: Session, principal: Principal, org_id: int | None = None) -> Organization:
    stmt = select(Organization).where(Organization.tenant_id == principal.tenant_id)
    if org_id:
        stmt = stmt.where(Organization.id == org_id)
    elif principal.organization_ids:
        stmt = stmt.where(Organization.id.in_(principal.organization_ids))
    org = db.execute(stmt.order_by(Organization.id)).scalars().first()
    if org is None:
        raise NotFoundError("Organization not found")
    return org


def get_period(db: Session, org: Organization, code: str | None) -> ReportingPeriod:
    stmt = select(ReportingPeriod).where(ReportingPeriod.organization_id == org.id)
    if code:
        stmt = stmt.where(ReportingPeriod.code == code)
        p = db.execute(stmt).scalars().first()
    else:
        # default: latest period that has any metric value
        from sqlalchemy import func

        from app.models.esg import MetricValue

        periods = db.execute(stmt.order_by(ReportingPeriod.end_date.desc())).scalars().all()
        counts = {x.id: (db.execute(select(func.count(MetricValue.id)).where(MetricValue.period_id == x.id)).scalar() or 0) for x in periods}
        p = max(periods, key=lambda x: (counts[x.id], x.end_date)) if periods else None
    if p is None:
        raise NotFoundError(f"Reporting period not found: {code}")
    return p


def get_entity(db: Session, principal: Principal, org: Organization, code: str | None) -> Entity:
    stmt = select(Entity).where(Entity.organization_id == org.id)
    if code:
        stmt = stmt.where(Entity.code == code)
    elif principal.entity_ids:
        # A scoped principal defaults to an entity it may actually see, not the group.
        stmt = stmt.where(Entity.id.in_(principal.entity_ids)).order_by(Entity.code)
    else:
        stmt = stmt.where(Entity.kind == "group")
    e = db.execute(stmt).scalars().first()
    if e is None:
        raise NotFoundError(f"Entity not found: {code}")
    if principal.entity_ids and e.id not in principal.entity_ids:
        from app.core.errors import PermissionError_

        raise PermissionError_("Not authorised for this entity")
    return e


def get_metric(db: Session, principal: Principal, code: str) -> MetricDefinition:
    m = db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == principal.tenant_id, MetricDefinition.code == code)).scalars().first()
    if m is None:
        raise NotFoundError(f"Metric not found: {code}")
    return m
