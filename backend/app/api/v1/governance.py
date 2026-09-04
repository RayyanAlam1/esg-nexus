"""Governance: policies, governance-as-code rules, issues (criticality), approvals, audit trail."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, Page, User, get_org, get_period, paginate, serialize
from app.core import audit
from app.core.errors import NotFoundError
from app.core.security import require
from app.engines.safe_expr import ExpressionError, evaluate
from app.models.audit import AuditLog
from app.models.governance import RULE_ACTIONS, SEVERITIES, Approval, GovernancePolicy, GovernanceRule, Issue
from app.models.identity import User as UserModel
from app.services.governance_service import run_metric_rules

router = APIRouter(prefix="/governance", tags=["governance"])


class RuleIn(BaseModel):
    code: str
    description: str
    severity: str = "MEDIUM"
    scope: str
    condition: str
    action: str
    message: str | None = None
    required_action: str | None = None
    owner: str | None = None
    version: str = "1.0"
    effective_date: date | None = None
    approval_status: str = "draft"
    policy_code: str | None = None


class RuleUpdate(BaseModel):
    description: str | None = None
    severity: str | None = None
    condition: str | None = None
    action: str | None = None
    message: str | None = None
    required_action: str | None = None
    is_active: bool | None = None
    approval_status: str | None = None
    version: str | None = None


class PolicyIn(BaseModel):
    code: str
    name: str
    category: str | None = None
    description: str | None = None
    owner: str | None = None
    version: str = "1.0"
    effective_date: date | None = None
    evidence_code: str | None = None


class IssueAction(BaseModel):
    comment: str | None = None


class ApprovalIn(BaseModel):
    object_type: str
    object_id: str
    assigned_to: int | None = None
    context: dict | None = None


class DecisionIn(BaseModel):
    decision: str  # approved|rejected|changes_requested
    comment: str | None = None


class TestRuleIn(BaseModel):
    condition: str
    context: dict


@router.get("/policies")
def policies(principal: User, db: DB):
    return serialize(db.execute(select(GovernancePolicy).where(GovernancePolicy.tenant_id == principal.tenant_id).order_by(GovernancePolicy.code)).scalars().all())


@router.post("/policies", dependencies=[Depends(require("governance.manage"))])
def create_policy(body: PolicyIn, principal: User, db: DB):
    p = GovernancePolicy(tenant_id=principal.tenant_id, status="active", **body.model_dump())
    db.add(p)
    db.flush()
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="policy.create",
        object_type="governance_policy",
        object_id=p.code,
        new_value=body.model_dump(mode="json"),
    )
    db.commit()
    return serialize(p)


@router.get("/rules")
def rules(principal: User, db: DB, scope: str | None = None):
    stmt = select(GovernanceRule).where(GovernanceRule.tenant_id == principal.tenant_id)
    if scope:
        stmt = stmt.where(GovernanceRule.scope == scope)
    return {
        "rules": serialize(db.execute(stmt.order_by(GovernanceRule.code)).scalars().all()),
        "actions": RULE_ACTIONS,
        "severities": SEVERITIES,
        "scopes": ["metric_value", "ai_output", "report", "data_change", "requirement"],
    }


@router.post("/rules", dependencies=[Depends(require("governance.manage"))])
def create_rule(body: RuleIn, principal: User, db: DB):
    try:
        evaluate(body.condition, {"metric": {}, "entity": {}, "period": {}, "report": {}})
    except ExpressionError as exc:
        if "Disallowed" in str(exc) or "Syntax" in str(exc) or "whitelisted" in str(exc):
            from app.core.errors import AppError

            raise AppError(f"Invalid condition: {exc}") from exc
    r = GovernanceRule(tenant_id=principal.tenant_id, is_active=body.approval_status == "approved", **body.model_dump())
    db.add(r)
    db.flush()
    audit.record(
        db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="rule.create", object_type="governance_rule", object_id=r.code, new_value=body.model_dump(mode="json")
    )
    db.commit()
    return serialize(r)


@router.put("/rules/{code}", dependencies=[Depends(require("governance.manage"))])
def update_rule(code: str, body: RuleUpdate, principal: User, db: DB):
    r = db.execute(select(GovernanceRule).where(GovernanceRule.tenant_id == principal.tenant_id, GovernanceRule.code == code)).scalars().first()
    if r is None:
        raise NotFoundError("Rule not found")
    old = serialize(r)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="rule.update",
        object_type="governance_rule",
        object_id=r.code,
        old_value=old,
        new_value=body.model_dump(exclude_none=True),
    )
    db.commit()
    return serialize(r)


@router.post("/rules/test")
def test_rule(body: TestRuleIn, principal: User):
    try:
        return {"result": bool(evaluate(body.condition, body.context))}
    except ExpressionError as exc:
        return {"error": str(exc)}


@router.post("/rules/run", dependencies=[Depends(require("metric.validate"))])
def run_rules(principal: User, db: DB, period: str | None = None, org_id: int | None = None):
    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    result = run_metric_rules(db, principal.tenant_id, org.id, p)
    audit.record(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        action="rules.run",
        object_type="reporting_period",
        object_id=p.code,
        new_value={k: v for k, v in result.items() if k != "triggered"},
    )
    db.commit()
    return result


@router.get("/issues")
def issues(
    principal: User,
    db: DB,
    page: Page = Depends(),
    severity: str | None = None,
    status: str | None = "open",
    category: str | None = None,
    metric: str | None = None,
    period: str | None = None,
):
    stmt = select(Issue).where(Issue.tenant_id == principal.tenant_id)
    if severity:
        stmt = stmt.where(Issue.severity == severity.upper())
    if status and status != "all":
        stmt = stmt.where(Issue.status.in_(["open", "acknowledged"]) if status == "open" else Issue.status == status)
    if category:
        stmt = stmt.where(Issue.category == category)
    if metric:
        stmt = stmt.where(Issue.metric_code == metric)
    if period:
        stmt = stmt.where(Issue.period_code == period)
    from sqlalchemy import case

    rank = case({"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}, value=Issue.severity, else_=5)
    result = paginate(db, stmt.order_by(rank, Issue.id.desc()), page, Issue)
    counts = {}
    for s in SEVERITIES:
        counts[s] = db.execute(select(Issue.id).where(Issue.tenant_id == principal.tenant_id, Issue.severity == s, Issue.status.in_(["open", "acknowledged"]))).all().__len__()
    result["open_by_severity"] = counts
    return result


def _issue(db, principal, code) -> Issue:
    i = db.execute(select(Issue).where(Issue.tenant_id == principal.tenant_id, Issue.code == code)).scalars().first()
    if i is None:
        raise NotFoundError("Issue not found")
    return i


@router.post("/issues/{code}/acknowledge", dependencies=[Depends(require("metric.validate"))])
def acknowledge(code: str, body: IssueAction, principal: User, db: DB):
    i = _issue(db, principal, code)
    i.status = "acknowledged"
    audit.record(db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="issue.acknowledge", object_type="issue", object_id=code, reason=body.comment)
    db.commit()
    return serialize(i)


@router.post("/issues/{code}/resolve", dependencies=[Depends(require("metric.approve"))])
def resolve(code: str, body: IssueAction, principal: User, db: DB):
    i = _issue(db, principal, code)
    i.status, i.resolved_by, i.resolution_note, i.resolved_at = "resolved", principal.user_id, body.comment, datetime.now(UTC)
    audit.record(db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="issue.resolve", object_type="issue", object_id=code, reason=body.comment)
    db.commit()
    return serialize(i)


@router.post("/issues/{code}/exception", dependencies=[Depends(require("governance.exception"))])
def approve_exception(code: str, body: IssueAction, principal: User, db: DB):
    i = _issue(db, principal, code)
    if not body.comment:
        from app.core.errors import AppError

        raise AppError("An exception requires a documented reason")
    i.status, i.resolved_by, i.resolution_note, i.resolved_at, i.blocks_report = "exception_approved", principal.user_id, body.comment, datetime.now(UTC), False
    db.add(
        Approval(
            tenant_id=principal.tenant_id,
            object_type="exception",
            object_id=code,
            state="approved",
            requested_by=principal.user_id,
            decided_by=principal.user_id,
            decision="approved",
            comment=body.comment,
            decided_at=datetime.now(UTC),
        )
    )
    audit.record(db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="issue.exception", object_type="issue", object_id=code, reason=body.comment)
    db.commit()
    return serialize(i)


@router.get("/approvals")
def approvals(principal: User, db: DB, pending: bool = True):
    stmt = select(Approval).where(Approval.tenant_id == principal.tenant_id)
    if pending:
        stmt = stmt.where(Approval.decision.is_(None))
    rows = db.execute(stmt.order_by(Approval.created_at.desc())).scalars().all()
    out = []
    for a in rows:
        req = db.get(UserModel, a.requested_by) if a.requested_by else None
        out.append({**serialize(a), "requested_by_email": req.email if req else None})
    return out


@router.post("/approvals", dependencies=[Depends(require("review"))])
def request_approval(body: ApprovalIn, principal: User, db: DB):
    a = Approval(tenant_id=principal.tenant_id, requested_by=principal.user_id, state="requires_review", **body.model_dump())
    db.add(a)
    db.flush()
    audit.record(db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="approval.request", object_type=body.object_type, object_id=body.object_id)
    db.commit()
    return serialize(a)


@router.post("/approvals/{approval_id}/decide", dependencies=[Depends(require("review"))])
def decide(approval_id: int, body: DecisionIn, principal: User, db: DB):
    a = db.get(Approval, approval_id)
    if a is None or a.tenant_id != principal.tenant_id:
        raise NotFoundError("Approval not found")
    if body.decision == "approved" and not principal.can_transition("approved") and a.object_type in ("report", "exception"):
        from app.core.errors import PermissionError_

        raise PermissionError_("Only approvers may approve reports/exceptions")
    a.decision, a.decided_by, a.comment, a.decided_at = body.decision, principal.user_id, body.comment, datetime.now(UTC)
    a.state = {"approved": "approved", "rejected": "rejected", "changes_requested": "requires_review"}.get(body.decision, a.state)
    audit.record(
        db, tenant_id=principal.tenant_id, user_id=principal.user_id, action=f"approval.{body.decision}", object_type=a.object_type, object_id=a.object_id, reason=body.comment
    )
    db.commit()
    return serialize(a)


# ------------------------------------------------------------------ audit trail
audit_router = APIRouter(prefix="/audit", tags=["audit"])


@audit_router.get("", dependencies=[Depends(require("audit.read"))])
def audit_log(
    principal: User,
    db: DB,
    page: Page = Depends(),
    action: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    user_id: int | None = None,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    stmt = select(AuditLog).where(AuditLog.tenant_id == principal.tenant_id)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    if object_type:
        stmt = stmt.where(AuditLog.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditLog.object_id.ilike(f"%{object_id}%"))
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if q:
        stmt = stmt.where(AuditLog.action.ilike(f"%{q}%") | AuditLog.object_id.ilike(f"%{q}%") | AuditLog.reason.ilike(f"%{q}%"))
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= datetime.combine(date_to, datetime.max.time()))
    result = paginate(db, stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()), page, AuditLog)
    users = {u.id: u.email for u in db.execute(select(UserModel).where(UserModel.tenant_id == principal.tenant_id)).scalars().all()}
    for item in result["items"]:
        item["user_email"] = users.get(item["user_id"])
    return result
