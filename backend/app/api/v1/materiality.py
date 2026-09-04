from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, User, get_org, serialize
from app.core import audit
from app.core.errors import NotFoundError
from app.core.security import require
from app.engines import metric_engine
from app.models.esg import MetricDefinition
from app.models.materiality import MaterialityAssessment, StakeholderInput
from app.models.organization import Entity, ReportingPeriod

router = APIRouter(prefix="/materiality", tags=["materiality"])


class TopicScoreIn(BaseModel):
    impact_severity: float | None = None
    impact_likelihood: float | None = None
    financial_magnitude: float | None = None
    financial_likelihood: float | None = None
    stakeholder_priority: float | None = None
    is_material: bool | None = None
    rationale: str | None = None


class StakeholderIn(BaseModel):
    stakeholder_group: str
    topic_code: str | None = None
    priority: float | None = None
    channel: str | None = None
    concern: str | None = None


def _assessment(db, principal, assessment_id: int | None = None) -> MaterialityAssessment:
    stmt = select(MaterialityAssessment).where(MaterialityAssessment.tenant_id == principal.tenant_id)
    if assessment_id:
        stmt = stmt.where(MaterialityAssessment.id == assessment_id)
    a = db.execute(stmt.order_by(MaterialityAssessment.id.desc())).scalars().first()
    if a is None:
        raise NotFoundError("Materiality assessment not found")
    return a


@router.get("/assessments")
def assessments(principal: User, db: DB):
    rows = db.execute(select(MaterialityAssessment).where(MaterialityAssessment.tenant_id == principal.tenant_id)).scalars().all()
    return [
        {**serialize(a), "period_code": db.get(ReportingPeriod, a.period_id).code, "topics": len(a.topics), "material_topics": len([t for t in a.topics if t.is_material])}
        for a in rows
    ]


@router.get("/assessments/{assessment_id}")
def assessment_detail(assessment_id: int, principal: User, db: DB):
    a = _assessment(db, principal, assessment_id)
    period = db.get(ReportingPeriod, a.period_id)
    org = get_org(db, principal)
    group = db.execute(select(Entity).where(Entity.organization_id == org.id, Entity.kind == "group")).scalars().first()
    topics = []
    for t in a.topics:
        related = []
        for code in t.related_metric_codes or []:
            m = db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == principal.tenant_id, MetricDefinition.code == code)).scalars().first()
            if m:
                v, _ = metric_engine.get_value(db, principal.tenant_id, code, group, period)
                related.append({"code": code, "name": m.name, "unit": m.unit, "value": v, "data_unavailable": v is None})
        topics.append({**serialize(t), "related_metrics": related, "x": t.financial_score, "y": t.impact_score, "size": t.stakeholder_priority})
    return {
        **serialize(a),
        "period_code": period.code,
        "topics": topics,
        "stakeholder_inputs": serialize(a.stakeholder_inputs),
        "matrix": {"x_axis": "Financial materiality (magnitude × likelihood / 5)", "y_axis": "Impact materiality (severity × likelihood / 5)", "threshold": a.threshold},
    }


@router.put("/assessments/{assessment_id}/topics/{topic_code}", dependencies=[Depends(require("metric.write"))])
def update_topic(assessment_id: int, topic_code: str, body: TopicScoreIn, principal: User, db: DB):
    a = _assessment(db, principal, assessment_id)
    t = next((x for x in a.topics if x.topic_code == topic_code), None)
    if t is None:
        raise NotFoundError("Topic not found")
    old = serialize(t)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    t.impact_score = round((t.impact_severity or 0) * (t.impact_likelihood or 0) / 5, 2)
    t.financial_score = round((t.financial_magnitude or 0) * (t.financial_likelihood or 0) / 5, 2)
    if body.is_material is None:
        t.is_material = max(t.impact_score, t.financial_score) >= a.threshold
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="materiality.update",
        object_type="materiality_topic",
        object_id=t.topic_code,
        old_value=old,
        new_value=body.model_dump(exclude_none=True),
    )
    db.commit()
    return serialize(t)


@router.post("/assessments/{assessment_id}/stakeholders", dependencies=[Depends(require("metric.write"))])
def add_stakeholder(assessment_id: int, body: StakeholderIn, principal: User, db: DB):
    a = _assessment(db, principal, assessment_id)
    s = StakeholderInput(assessment_id=a.id, **body.model_dump())
    db.add(s)
    db.commit()
    return serialize(s)


@router.post("/analyze", dependencies=[Depends(require("ai.run"))])
def analyze(principal: User, db: DB, period: str | None = None):
    from app.ai.agents import registry

    res = registry.get("materiality_agent")(db, principal).run("assess", {"period_code": period or "", "question": "Assess the materiality results and recommend changes."})
    db.commit()
    return res.as_dict()
