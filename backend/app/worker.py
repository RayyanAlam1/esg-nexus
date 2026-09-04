"""Background worker (task queue abstraction).

Uses Redis lists when ESG_REDIS_URL is set (Celery/RQ-compatible pattern), otherwise runs scheduled
maintenance in-process: nightly recalculation, data-quality assessment and governance rule evaluation.
Kept intentionally small: job functions are plain callables registered in JOBS so any queue can drive them.
"""

from __future__ import annotations

import json
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.engines import data_quality, metric_engine
from app.models.identity import Tenant
from app.models.organization import Organization, ReportingPeriod
from app.services.governance_service import run_metric_rules

configure_logging()
log = get_logger("worker")


def job_recompute(period_code: str | None = None) -> dict:
    out = {}
    with SessionLocal() as db:
        for tenant in db.execute(select(Tenant)).scalars().all():
            for org in db.execute(select(Organization).where(Organization.tenant_id == tenant.id)).scalars().all():
                stmt = select(ReportingPeriod).where(ReportingPeriod.organization_id == org.id)
                if period_code:
                    stmt = stmt.where(ReportingPeriod.code == period_code)
                for period in db.execute(stmt).scalars().all():
                    calcs = metric_engine.recalculate_all(db, tenant.id, org.id, period)
                    data_quality.assess_all(db, tenant.id, org.id, period)
                    gov = run_metric_rules(db, tenant.id, org.id, period)
                    db.commit()
                    out[f"{org.code}:{period.code}"] = {"calculations": len(calcs), "issues": gov["issues_triggered"]}
    return out


JOBS = {"recompute": job_recompute}


def main() -> None:
    settings = get_settings()
    if settings.redis_url:
        try:
            import redis  # type: ignore

            r = redis.Redis.from_url(settings.redis_url)
            log.info("worker listening", queue="esg:jobs")
            while True:
                item = r.blpop("esg:jobs", timeout=30)
                if item is None:
                    continue
                payload = json.loads(item[1])
                fn = JOBS.get(payload.get("job"))
                if fn:
                    log.info("job start", job=payload.get("job"))
                    result = fn(**payload.get("kwargs", {}))
                    log.info("job done", job=payload.get("job"), result=result)
        except ImportError:
            log.warning("redis package not installed; falling back to scheduled loop")
    while True:
        log.info("scheduled recompute")
        try:
            job_recompute()
        except Exception as exc:  # pragma: no cover
            log.error("recompute failed", error=str(exc))
        time.sleep(6 * 3600)


if __name__ == "__main__":
    main()
