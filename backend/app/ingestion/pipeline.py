"""Ingestion pipeline: source → raw layer → validation → normalisation → quality → transformation → metric engine.

Every ingestion event records source, timestamp, user, file metadata, version, status, validation result and
transformation history. Loading into metric values respects governance (data_change rules) and evidence.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import guardrails
from app.core import audit
from app.core.security import Principal
from app.engines import data_quality
from app.ingestion.connectors import CONNECTORS, detect_kind
from app.models.data import Dataset, DatasetRecord, DatasetVersion, DataSource
from app.models.esg import MetricDefinition, MetricValue
from app.models.organization import Entity, ReportingPeriod
from app.services.governance_service import check_data_change

REQUIRED = ["metric_code", "value"]
ALIASES = {
    "metric": "metric_code",
    "code": "metric_code",
    "entity": "entity_code",
    "company": "entity_code",
    "period": "period_code",
    "year": "period_code",
    "fy": "period_code",
    "amount": "value",
    "val": "value",
}


def _normalise_row(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        key = ALIASES.get(k.strip().lower(), k.strip().lower())
        out[key] = v
    if "period_code" in out and isinstance(out["period_code"], (int, float)):
        out["period_code"] = f"FY{int(out['period_code'])}"
    if "period_code" in out and isinstance(out["period_code"], str) and out["period_code"].isdigit():
        out["period_code"] = f"FY{out['period_code']}"
    return out


class IngestionPipeline:
    def __init__(self, db: Session, principal: Principal):
        self.db = db
        self.principal = principal

    def ingest(
        self,
        *,
        source_code: str,
        dataset_code: str,
        dataset_name: str | None,
        file_name: str,
        data: bytes,
        kind: str | None = None,
        idempotency_key: str | None = None,
        entity_default: str | None = None,
        period_default: str | None = None,
        auto_load: bool = True,
    ) -> dict:
        guard = guardrails.check_input("", file_name=file_name)
        if guard.blocked:
            return {"status": "rejected", "guardrail": guard.as_dict()}
        source = self.db.execute(select(DataSource).where(DataSource.tenant_id == self.principal.tenant_id, DataSource.code == source_code)).scalars().first()
        if source is None:
            raise ValueError(f"Unknown data source {source_code}")
        dataset = self.db.execute(select(Dataset).where(Dataset.tenant_id == self.principal.tenant_id, Dataset.code == dataset_code)).scalars().first()
        if dataset is None:
            dataset = Dataset(tenant_id=self.principal.tenant_id, source_id=source.id, code=dataset_code, name=dataset_name or dataset_code)
            self.db.add(dataset)
            self.db.flush()
        if idempotency_key:
            existing = self.db.execute(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset.id, DatasetVersion.idempotency_key == idempotency_key)).scalars().first()
            if existing:
                return {"status": "duplicate", "dataset_version_id": existing.id, "version": existing.version}
        kind = kind or detect_kind(file_name)
        reader = CONNECTORS.get(kind)
        if reader is None:
            raise ValueError(f"No connector for kind {kind}")
        # RAW LAYER
        file_hash = hashlib.sha256(data).hexdigest()
        version_no = max([v.version for v in dataset.versions] or [0]) + 1
        dv = DatasetVersion(
            tenant_id=self.principal.tenant_id,
            dataset_id=dataset.id,
            version=version_no,
            file_name=file_name,
            file_hash=file_hash,
            uploaded_by=self.principal.user_id,
            status="received",
            idempotency_key=idempotency_key,
            transformation_history=[{"step": "received", "at": datetime.now(UTC).isoformat(), "connector": kind}],
        )
        self.db.add(dv)
        self.db.flush()
        rows = reader(data, file_name)
        # VALIDATION + NORMALISATION
        metrics = {m.code: m for m in self.db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == self.principal.tenant_id)).scalars().all()}
        entities = {e.code: e for e in self.db.execute(select(Entity).where(Entity.tenant_id == self.principal.tenant_id)).scalars().all()}
        periods = {p.code: p for p in self.db.execute(select(ReportingPeriod).where(ReportingPeriod.tenant_id == self.principal.tenant_id)).scalars().all()}
        valid_rows, issues_total = 0, 0
        records = []
        if kind in ("pdf", "text"):
            for i, r in enumerate(rows):
                records.append(DatasetRecord(version_id=dv.id, row_index=i, payload=r, is_valid=True, issues=[], metric_code=None))
            dv.status = "validated"
            dv.validation_result = {"valid": True, "rows": len(rows), "note": "Document extracted; run the ESG Data Agent to map candidate facts to metrics."}
        else:
            for i, raw in enumerate(rows):
                row = _normalise_row(raw)
                issues = []
                mcode = str(row.get("metric_code") or "").strip()
                metric = metrics.get(mcode)
                if metric is None:
                    issues.append({"type": "unknown_metric", "severity": "HIGH", "detail": mcode or "missing metric_code"})
                ecode = str(row.get("entity_code") or entity_default or "").strip()
                pcode = str(row.get("period_code") or period_default or "").strip()
                if ecode not in entities:
                    issues.append({"type": "unknown_entity", "severity": "HIGH", "detail": ecode or "missing entity_code"})
                if pcode not in periods:
                    issues.append({"type": "unknown_period", "severity": "HIGH", "detail": pcode or "missing period_code"})
                value = row.get("value")
                value_text = None
                if metric is not None:
                    issues += guardrails.validate_esg_value({"data_type": metric.data_type, "validation_rules": metric.validation_rules}, value)
                    if metric.data_type == "text":
                        value_text, value = str(value) if value is not None else None, None
                is_valid = not any(i["severity"] == "HIGH" for i in issues)
                valid_rows += int(is_valid)
                issues_total += len(issues)
                records.append(
                    DatasetRecord(
                        version_id=dv.id,
                        row_index=i,
                        payload=raw,
                        metric_code=mcode or None,
                        entity_code=ecode or None,
                        period_code=pcode or None,
                        value=float(value) if isinstance(value, (int, float)) else None,
                        value_text=value_text,
                        unit=row.get("unit"),
                        is_valid=is_valid,
                        issues=issues,
                    )
                )
            dv.status = "validated" if valid_rows else "failed"
            dv.validation_result = {"valid": valid_rows == len(rows), "rows": len(rows), "valid_rows": valid_rows, "issues": issues_total}
        self.db.add_all(records)
        dv.row_count = len(rows)
        dv.transformation_history.append({"step": "validated", "at": datetime.now(UTC).isoformat(), "valid_rows": valid_rows})
        dv.quality = (
            data_quality.dataset_quality(
                [{**r.payload, "_valid": r.is_valid, "metric_code": r.metric_code, "entity_code": r.entity_code, "period_code": r.period_code} for r in records],
                ["metric_code", "value"],
            )
            if kind not in ("pdf", "text")
            else None
        )
        self.db.flush()
        loaded = 0
        if auto_load and kind not in ("pdf", "text"):
            loaded = self.load(dv, metrics, entities, periods)
        audit.record(
            self.db,
            tenant_id=self.principal.tenant_id,
            user_id=self.principal.user_id,
            action="data.upload",
            object_type="dataset_version",
            object_id=dv.id,
            new_value={"dataset": dataset.code, "file": file_name, "hash": file_hash, "rows": len(rows), "loaded": loaded},
        )
        return {
            "status": dv.status,
            "dataset_version_id": dv.id,
            "version": dv.version,
            "rows": len(rows),
            "valid_rows": valid_rows,
            "loaded_values": loaded,
            "quality": dv.quality,
            "validation_result": dv.validation_result,
        }

    def load(self, dv: DatasetVersion, metrics=None, entities=None, periods=None) -> int:
        metrics = metrics or {m.code: m for m in self.db.execute(select(MetricDefinition).where(MetricDefinition.tenant_id == self.principal.tenant_id)).scalars().all()}
        entities = entities or {e.code: e for e in self.db.execute(select(Entity).where(Entity.tenant_id == self.principal.tenant_id)).scalars().all()}
        periods = periods or {p.code: p for p in self.db.execute(select(ReportingPeriod).where(ReportingPeriod.tenant_id == self.principal.tenant_id)).scalars().all()}
        loaded = 0
        for rec in dv.records:
            if not rec.is_valid or not rec.metric_code:
                continue
            metric, entity, period = metrics.get(rec.metric_code), entities.get(rec.entity_code), periods.get(rec.period_code)
            if not (metric and entity and period):
                continue
            check_data_change(self.db, self.principal.tenant_id, period=period, object_type="metric_value", roles=self.principal.roles)
            mv = (
                self.db.execute(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.entity_id == entity.id, MetricValue.period_id == period.id))
                .scalars()
                .first()
            )
            old = {"value": mv.value_numeric if mv else None}
            if mv is None:
                mv = MetricValue(tenant_id=self.principal.tenant_id, metric_id=metric.id, entity_id=entity.id, period_id=period.id, created_by=self.principal.user_id)
                self.db.add(mv)
            elif mv.status in ("approved", "final") and mv.source_type == "reported":
                rec.issues = (rec.issues or []) + [
                    {"type": "locked_value", "severity": "MEDIUM", "detail": "Existing reported/approved value retained; ingested value stored on the record for review."}
                ]
                continue
            mv.value_numeric, mv.value_text = rec.value, rec.value_text
            mv.unit = rec.unit or metric.unit
            mv.status, mv.source_type, mv.dataset_version_id = "draft", "ingested", dv.id
            loaded += 1
            audit.record(
                self.db,
                tenant_id=self.principal.tenant_id,
                user_id=self.principal.user_id,
                action="data.modify",
                object_type="metric_value",
                object_id=f"{metric.code}/{entity.code}/{period.code}",
                old_value=old,
                new_value={"value": rec.value},
                reason=f"Ingested from dataset version {dv.id}",
            )
        dv.status = "loaded"
        dv.transformation_history.append({"step": "loaded", "at": datetime.now(UTC).isoformat(), "values": loaded})
        self.db.flush()
        return loaded
