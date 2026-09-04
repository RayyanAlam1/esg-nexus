from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, Page, User, get_org, get_period, paginate, serialize
from app.core.errors import NotFoundError
from app.core.security import require
from app.models.organization import Organization, ReportingPeriod
from app.models.reporting import Report, ReportVersion
from app.reports.builder import ReportBuilder
from app.reports.renderers import html_renderer
from app.reports.templates import load_templates

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportIn(BaseModel):
    period_code: str
    template_code: str = "ESG_ANNUAL"
    title: str | None = None
    framework_codes: list[str] = ["WEF_SCM", "UNGC", "UN_SDG"]
    scope: dict | None = None
    org_id: int | None = None


class SectionIn(BaseModel):
    state: str | None = None
    content_md: str | None = None
    comment: str | None = None


class TransitionIn(BaseModel):
    state: str
    comment: str | None = None


@router.get("/templates")
def templates(principal: User):
    return load_templates()


@router.get("")
def list_reports(principal: User, db: DB, page: Page = Depends(), status: str | None = None):
    stmt = select(Report).where(Report.tenant_id == principal.tenant_id)
    if status:
        stmt = stmt.where(Report.status == status)
    result = paginate(db, stmt.order_by(Report.created_at.desc()), page, Report)
    for item in result["items"]:
        r = db.get(Report, item["id"])
        item["period_code"] = db.get(ReportingPeriod, r.period_id).code
        item["organization_name"] = db.get(Organization, r.organization_id).name
        item["section_count"] = len(r.sections)
        item["approved_sections"] = len([s for s in r.sections if s.status in ("approved", "published")])
        item["versions"] = len(r.versions)
    return result


@router.post("", dependencies=[Depends(require("report.build"))])
def create_report(body: ReportIn, principal: User, db: DB):
    org = get_org(db, principal, body.org_id)
    p = get_period(db, org, body.period_code)
    r = ReportBuilder(db, principal).create(
        organization_id=org.id, period_id=p.id, template_code=body.template_code, title=body.title, framework_codes=body.framework_codes, scope=body.scope
    )
    db.commit()
    return report_detail(r.id, principal, db)


@router.get("/{report_id}")
def report_detail(report_id: int, principal: User, db: DB):
    r = ReportBuilder(db, principal).report(report_id)
    return {
        **serialize(r),
        "period_code": db.get(ReportingPeriod, r.period_id).code,
        "organization_name": db.get(Organization, r.organization_id).name,
        "sections": serialize(r.sections),
        "versions": serialize(r.versions),
    }


@router.post("/{report_id}/generate-draft", dependencies=[Depends(require("report.build"))])
def generate_draft(report_id: int, principal: User, db: DB, sections: str | None = None):
    r = ReportBuilder(db, principal).generate_draft(report_id, sections=[s for s in sections.split(",") if s] if sections else None)
    db.commit()
    return report_detail(r.id, principal, db)


@router.post("/{report_id}/validate", dependencies=[Depends(require("report.build"))])
def validate(report_id: int, principal: User, db: DB):
    result = ReportBuilder(db, principal).validate(report_id)
    db.commit()
    return result


@router.get("/{report_id}/preview")
def preview(report_id: int, principal: User, db: DB):
    b = ReportBuilder(db, principal)
    payload = b.render_payload(report_id)
    payload["watermark"] = None if payload["status"] in ("approved", "published") else "DRAFT — NOT FOR DISTRIBUTION"
    return {"pages": html_renderer.pages(payload), "css": html_renderer.CSS, "title": payload["title"], "status": payload["status"], "readiness": payload["readiness"]}


@router.get("/{report_id}/preview.html", response_class=HTMLResponse)
def preview_html(report_id: int, principal: User, db: DB):
    b = ReportBuilder(db, principal)
    payload = b.render_payload(report_id)
    payload["watermark"] = None if payload["status"] in ("approved", "published") else "DRAFT — NOT FOR DISTRIBUTION"
    return HTMLResponse(html_renderer.render(payload).decode("utf-8"))


@router.put("/{report_id}/sections/{section_code}")
def update_section(report_id: int, section_code: str, body: SectionIn, principal: User, db: DB):
    b = ReportBuilder(db, principal)
    state = body.state or "requires_review"
    if body.content_md is not None and not principal.has("report.build") and not principal.has("review"):
        from app.core.errors import PermissionError_

        raise PermissionError_("Not permitted to edit sections")
    s = b.transition_section(report_id, section_code, state, comment=body.comment, content_md=body.content_md)
    db.commit()
    return serialize(s)


@router.post("/{report_id}/sections/{section_code}/regenerate", dependencies=[Depends(require("report.build"))])
def regenerate(report_id: int, section_code: str, principal: User, db: DB):
    r = ReportBuilder(db, principal).generate_draft(report_id, sections=[section_code])
    db.commit()
    return serialize(next(s for s in r.sections if s.code == section_code))


@router.post("/{report_id}/transition")
def transition(report_id: int, body: TransitionIn, principal: User, db: DB):
    r = ReportBuilder(db, principal).transition_report(report_id, body.state, comment=body.comment)
    db.commit()
    return report_detail(r.id, principal, db)


@router.post("/{report_id}/generate")
def generate(report_id: int, principal: User, db: DB, format: str = "pdf", final: bool = False):
    from app.core.errors import PermissionError_

    if final and not principal.has("report.approve"):
        raise PermissionError_("Final generation requires the Report Approver role")
    if not final and not (principal.has("report.build") or principal.has("report.approve") or principal.has("review")):
        raise PermissionError_("Draft generation requires report.build, review or report.approve")
    rv = ReportBuilder(db, principal).generate(report_id, format, final=final)
    db.commit()
    return serialize(rv)


@router.get("/{report_id}/versions")
def versions(report_id: int, principal: User, db: DB):
    r = ReportBuilder(db, principal).report(report_id)
    return serialize(r.versions)


@router.get("/versions/{version_id}/download")
def download(version_id: int, principal: User, db: DB):
    rv = db.get(ReportVersion, version_id)
    if rv is None or rv.tenant_id != principal.tenant_id:
        raise NotFoundError("Version not found")
    path = Path(rv.storage_key)
    if not path.exists():
        raise NotFoundError("File missing from storage")
    media = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
        "html": "text/html",
    }[rv.format]
    return FileResponse(path, media_type=media, filename=path.name)
