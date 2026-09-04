"""Data lineage: Report Metric → Value → Formula → Inputs → Dataset → Source → Evidence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data import Dataset, DatasetVersion, DataSource
from app.models.esg import CalculationRun, MetricDefinition, MetricValue
from app.models.evidence import Evidence, EvidenceLink
from app.models.organization import Entity, ReportingPeriod


def _node(kind: str, key: str, label: str, **meta) -> dict:
    return {"id": f"{kind}:{key}", "kind": kind, "label": label, "meta": meta}


def build(db: Session, tenant_id: int, metric: MetricDefinition, entity: Entity, period: ReportingPeriod, *, depth: int = 0, _seen: set | None = None) -> dict:
    """Return {nodes: [...], edges: [...]} for the lineage graph of one reported value."""
    seen = _seen if _seen is not None else set()
    nodes: list[dict] = []
    edges: list[dict] = []
    key = f"{metric.code}|{entity.code}|{period.code}"
    if key in seen:
        return {"nodes": nodes, "edges": edges}
    seen.add(key)

    mv = db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == period.id)).scalars().first()
    root = _node(
        "metric",
        key,
        f"{metric.name} [{entity.code}, {period.code}]",
        code=metric.code,
        unit=metric.unit,
        value=mv.value_numeric if mv else None,
        status=mv.status if mv else "unavailable",
        source_type=mv.source_type if mv else None,
    )
    nodes.append(root)
    if mv is None:
        return {"nodes": nodes, "edges": edges}

    # Calculation
    run = None
    if mv.calculation_run_id:
        run = db.get(CalculationRun, mv.calculation_run_id)
    elif metric.formula:
        run = (
            db.execute(
                select(CalculationRun)
                .where(CalculationRun.metric_id == metric.id, CalculationRun.entity_id == entity.id, CalculationRun.period_id == period.id)
                .order_by(CalculationRun.executed_at.desc())
            )
            .scalars()
            .first()
        )
    if run is not None:
        cn = _node(
            "calculation",
            str(run.id),
            f"Calculation v{run.calculation_version}",
            formula=run.formula,
            status=run.status,
            result=run.result,
            executed_at=run.executed_at.isoformat() if run.executed_at else None,
        )
        nodes.append(cn)
        edges.append({"from": root["id"], "to": cn["id"], "relation": "calculated_by"})
        for code, inp in (run.inputs or {}).items():
            base_code = code.split("@")[0]
            im = db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == tenant_id, MetricDefinition.code == base_code)).scalars().first()
            ie = db.execute(select(Entity).where(Entity.tenant_id == tenant_id, Entity.code == inp.get("entity"))).scalars().first()
            ip = (
                db.execute(
                    select(ReportingPeriod).where(
                        ReportingPeriod.tenant_id == tenant_id, ReportingPeriod.code == inp.get("period"), ReportingPeriod.organization_id == entity.organization_id
                    )
                )
                .scalars()
                .first()
            )
            if im and ie and ip and depth < 4:
                sub = build(db, tenant_id, im, ie, ip, depth=depth + 1, _seen=seen)
                nodes.extend(sub["nodes"])
                edges.extend(sub["edges"])
                edges.append({"from": cn["id"], "to": f"metric:{im.code}|{ie.code}|{ip.code}", "relation": "input"})
            else:
                inn = _node("input", f"{code}|{inp.get('entity')}|{inp.get('period')}", f"{code} = {inp.get('value')}", **inp)
                nodes.append(inn)
                edges.append({"from": cn["id"], "to": inn["id"], "relation": "input"})

    # Dataset / source
    if mv.dataset_version_id:
        dv = db.get(DatasetVersion, mv.dataset_version_id)
        if dv is not None:
            ds = db.get(Dataset, dv.dataset_id)
            src = db.get(DataSource, ds.source_id) if ds else None
            dn = _node(
                "dataset",
                str(dv.id),
                f"{ds.name} v{dv.version}" if ds else f"Dataset version {dv.id}",
                file_name=dv.file_name,
                file_hash=dv.file_hash,
                status=dv.status,
                uploaded_at=dv.uploaded_at.isoformat() if dv.uploaded_at else None,
            )
            nodes.append(dn)
            edges.append({"from": root["id"], "to": dn["id"], "relation": "loaded_from"})
            if src is not None:
                sn = _node("source", src.code, src.name, source_kind=src.kind, system=src.system_name, owner=src.owner)
                nodes.append(sn)
                edges.append({"from": dn["id"], "to": sn["id"], "relation": "originates_from"})

    # Evidence
    links = (
        db.execute(select(EvidenceLink).where((EvidenceLink.metric_value_id == mv.id) | ((EvidenceLink.metric_id == metric.id) & (EvidenceLink.metric_value_id.is_(None)))))
        .scalars()
        .all()
    )
    for link in links:
        ev = db.get(Evidence, link.evidence_id)
        if ev is None:
            continue
        if ev.period_id and ev.period_id != period.id:
            continue
        en = _node(
            "evidence",
            ev.code,
            ev.title,
            evidence_kind=ev.kind,
            document=ev.document_ref,
            page=ev.printed_page,
            pdf_page=ev.page_from,
            verification=ev.verification_status,
            hash=ev.file_hash,
            excerpt=(ev.excerpt or "")[:300],
        )
        nodes.append(en)
        edges.append({"from": root["id"], "to": en["id"], "relation": link.relation})

    # de-duplicate nodes by id
    uniq: dict[str, dict] = {}
    for n in nodes:
        uniq.setdefault(n["id"], n)
    return {"nodes": list(uniq.values()), "edges": edges}


def chain(db: Session, tenant_id: int, metric: MetricDefinition, entity: Entity, period: ReportingPeriod) -> list[str]:
    """Textual lineage chain (I7 example format)."""
    g = build(db, tenant_id, metric, entity, period)
    by_id = {n["id"]: n for n in g["nodes"]}
    root = g["nodes"][0] if g["nodes"] else None
    if root is None:
        return []
    out = [f"{root['label']} → {root['meta'].get('value')} {root['meta'].get('unit') or ''}".strip()]
    for e in g["edges"]:
        if e["from"] == root["id"]:
            n = by_id.get(e["to"])
            if n:
                out.append(f"→ {n['kind']}: {n['label']}")
    return out
