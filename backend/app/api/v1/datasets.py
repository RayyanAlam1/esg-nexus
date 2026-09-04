"""Data sources, datasets, ingestion (upload → validate → load), data quality, lineage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, Page, User, get_entity, get_metric, get_org, get_period, paginate, serialize
from app.core import audit
from app.core.errors import NotFoundError
from app.core.security import require
from app.engines import data_quality, lineage
from app.ingestion import IngestionPipeline, detect_kind
from app.models.ai import QualityScore
from app.models.data import Dataset, DatasetRecord, DatasetVersion, DataSource
from app.models.esg import MetricDefinition
from app.models.organization import Entity

router = APIRouter(prefix="/datasets", tags=["data"])


class SourceIn(BaseModel):
    code: str
    name: str
    kind: str
    system_name: str | None = None
    owner: str | None = None
    description: str | None = None
    config: dict | None = None


@router.get("/sources")
def sources(principal: User, db: DB):
    rows = db.execute(select(DataSource).where(DataSource.tenant_id == principal.tenant_id).order_by(DataSource.code)).scalars().all()
    return [{**serialize(s), "dataset_count": len(s.datasets)} for s in rows]


@router.post("/sources", dependencies=[Depends(require("admin"))])
def create_source(body: SourceIn, principal: User, db: DB):
    org = get_org(db, principal)
    s = DataSource(tenant_id=principal.tenant_id, organization_id=org.id, **body.model_dump())
    db.add(s)
    db.flush()
    audit.record(
        db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="data_source.create", object_type="data_source", object_id=s.code, new_value=body.model_dump()
    )
    db.commit()
    return serialize(s)


@router.get("")
def list_datasets(principal: User, db: DB, page: Page = Depends(), source: str | None = None, pillar: str | None = None):
    stmt = select(Dataset).where(Dataset.tenant_id == principal.tenant_id)
    if source:
        stmt = stmt.join(DataSource, DataSource.id == Dataset.source_id).where(DataSource.code == source)
    if pillar:
        stmt = stmt.where(Dataset.pillar == pillar)
    result = paginate(db, stmt.order_by(Dataset.code), page, Dataset)
    for item in result["items"]:
        ds = db.get(Dataset, item["id"])
        latest = ds.versions[-1] if ds.versions else None
        item["source_code"], item["source_name"], item["source_kind"] = ds.source.code, ds.source.name, ds.source.kind
        item["latest_version"] = serialize(latest, exclude={"transformation_history"}) if latest else None
        item["version_count"] = len(ds.versions)
    return result


@router.get("/{dataset_id}")
def dataset_detail(dataset_id: int, principal: User, db: DB):
    ds = db.get(Dataset, dataset_id)
    if ds is None or ds.tenant_id != principal.tenant_id:
        raise NotFoundError("Dataset not found")
    return {**serialize(ds), "source": serialize(ds.source), "versions": serialize(ds.versions)}


@router.get("/versions/{version_id}/records")
def records(version_id: int, principal: User, db: DB, page: Page = Depends(), only_invalid: bool = False):
    dv = db.get(DatasetVersion, version_id)
    if dv is None or dv.tenant_id != principal.tenant_id:
        raise NotFoundError("Dataset version not found")
    stmt = select(DatasetRecord).where(DatasetRecord.version_id == dv.id)
    if only_invalid:
        stmt = stmt.where(DatasetRecord.is_valid == False)  # noqa: E712
    return paginate(db, stmt.order_by(DatasetRecord.row_index), page, DatasetRecord)


@router.post("/upload", dependencies=[Depends(require("data.write"))])
async def upload(
    principal: User,
    db: DB,
    file: UploadFile = File(...),
    source_code: str = Form("SRC-MANUAL"),
    dataset_code: str = Form(...),
    dataset_name: str | None = Form(None),
    entity_default: str | None = Form(None),
    period_default: str | None = Form(None),
    auto_load: bool = Form(True),
    idempotency_key: str | None = Form(None),
):
    data = await file.read()
    pipeline = IngestionPipeline(db, principal)
    result = pipeline.ingest(
        source_code=source_code,
        dataset_code=dataset_code,
        dataset_name=dataset_name,
        file_name=file.filename or "upload",
        data=data,
        kind=detect_kind(file.filename or ""),
        idempotency_key=idempotency_key,
        entity_default=entity_default,
        period_default=period_default,
        auto_load=auto_load,
    )
    db.commit()
    return result


@router.post("/versions/{version_id}/load", dependencies=[Depends(require("data.write"))])
def load_version(version_id: int, principal: User, db: DB):
    dv = db.get(DatasetVersion, version_id)
    if dv is None or dv.tenant_id != principal.tenant_id:
        raise NotFoundError("Dataset version not found")
    loaded = IngestionPipeline(db, principal).load(dv)
    db.commit()
    return {"loaded_values": loaded, "status": dv.status}


class ClassifyIn(BaseModel):
    columns: list[str]
    rows: list[dict] = []


@router.post("/classify", dependencies=[Depends(require("ai.run"))])
def classify(body: ClassifyIn, principal: User, db: DB):
    """ESG Data Agent: propose column → metric mappings and detect missing/inconsistent values."""
    from app.ai.agents import registry

    agent = registry.get("esg_data_agent")(db, principal)
    res = agent.run("classify_dataset", body.model_dump())
    db.commit()
    return res.as_dict()


# ------------------------------------------------------------------ quality
quality_router = APIRouter(prefix="/quality", tags=["data"])


@quality_router.get("/summary")
def quality_summary(principal: User, db: DB, period: str | None = None, org_id: int | None = None):
    org = get_org(db, principal, org_id)
    p = get_period(db, org, period)
    entity_ids = [e.id for e in db.execute(select(Entity).where(Entity.organization_id == org.id)).scalars().all()]
    rows = db.execute(select(QualityScore).where(QualityScore.period_id == p.id, QualityScore.entity_id.in_(entity_ids))).scalars().all()
    dims = ["completeness", "accuracy", "consistency", "timeliness", "validity", "uniqueness", "traceability"]
    avg = {d: round(sum(getattr(r, d) for r in rows) / len(rows), 1) if rows else 0 for d in dims}
    overall = round(sum(r.overall for r in rows) / len(rows), 1) if rows else 0
    by_pillar: dict[str, list[float]] = {}
    lowest = []
    for r in rows:
        m = db.get(MetricDefinition, r.metric_id)
        by_pillar.setdefault(m.pillar, []).append(r.overall)
        lowest.append((r.overall, m.code, m.name, db.get(Entity, r.entity_id).code, r.explanation))
    lowest.sort(key=lambda x: x[0])
    return {
        "period": p.code,
        "overall": overall,
        "dimensions": avg,
        "assessed_values": len(rows),
        "by_pillar": {k: round(sum(v) / len(v), 1) for k, v in by_pillar.items()},
        "lowest": [{"score": s, "metric_code": c, "metric_name": n, "entity": e, "explanation": x} for s, c, n, e, x in lowest[:15]],
    }


@quality_router.get("/scores")
def quality_scores(
    principal: User, db: DB, page: Page = Depends(), period: str | None = None, metric: str | None = None, entity: str | None = None, max_score: float | None = None
):
    org = get_org(db, principal)
    p = get_period(db, org, period)
    stmt = select(QualityScore).where(QualityScore.tenant_id == principal.tenant_id, QualityScore.period_id == p.id)
    if metric:
        stmt = stmt.where(QualityScore.metric_id == get_metric(db, principal, metric).id)
    if entity:
        stmt = stmt.where(QualityScore.entity_id == get_entity(db, principal, org, entity).id)
    if max_score is not None:
        stmt = stmt.where(QualityScore.overall <= max_score)
    result = paginate(db, stmt.order_by(QualityScore.overall), page, QualityScore)
    for item in result["items"]:
        item["metric_code"] = db.get(MetricDefinition, item["metric_id"]).code
        item["metric_name"] = db.get(MetricDefinition, item["metric_id"]).name
        item["entity_code"] = db.get(Entity, item["entity_id"]).code
    return result


@quality_router.post("/assess", dependencies=[Depends(require("metric.validate"))])
def assess(principal: User, db: DB, period: str | None = None, metric: str | None = None, entity: str | None = None):
    org = get_org(db, principal)
    p = get_period(db, org, period)
    if metric:
        r = data_quality.assess(db, principal.tenant_id, get_metric(db, principal, metric), get_entity(db, principal, org, entity), p)
        db.commit()
        return {"metric": r.metric_code, "entity": r.entity_code, "scores": r.scores, "overall": r.overall, "explanation": r.explanation}
    results = data_quality.assess_all(db, principal.tenant_id, org.id, p)
    db.commit()
    return {"assessed": len(results), "average": round(sum(r.overall for r in results) / len(results), 1) if results else 0}


lineage_router = APIRouter(prefix="/lineage", tags=["data"])


@lineage_router.get("")
def get_lineage(principal: User, db: DB, metric: str, entity: str | None = None, period: str | None = None):
    org = get_org(db, principal)
    m = get_metric(db, principal, metric)
    e = get_entity(db, principal, org, entity)
    p = get_period(db, org, period)
    return {"graph": lineage.build(db, principal.tenant_id, m, e, p), "chain": lineage.chain(db, principal.tenant_id, m, e, p)}
