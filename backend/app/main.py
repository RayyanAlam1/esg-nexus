"""ESG Nexus API — FastAPI application factory."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.api.v1.admin import health_router
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.core.errors import envelope, install_error_handlers
from app.core.logging import configure_logging, get_logger

settings = get_settings()
configure_logging()
log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import app.models  # noqa: F401 — register models

    if settings.environment in ("development", "test"):
        Base.metadata.create_all(engine)  # production uses `alembic upgrade head`
    if settings.auto_seed:
        from app.seed import seed_if_needed

        with SessionLocal() as db:
            seed_if_needed(db)
    log.info("startup complete", environment=settings.environment, ai_provider=settings.ai_provider)
    yield


app = FastAPI(
    title="ESG Nexus API",
    version="1.0.0",
    description="Enterprise ESG Intelligence, Governance & Reporting Platform — versioned REST API. Every number is traceable to evidence; AI outputs pass guardrails, evaluation and governance before use.",
    lifespan=lifespan,
    openapi_url=f"{settings.api_prefix}/openapi.json",
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
)
install_error_handlers(app)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_buckets: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def observability_and_security(request: Request, call_next):
    """Request id, structured access log, latency header, simple per-IP rate limiting, security headers."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _buckets[ip]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= settings.rate_limit_per_minute:
        return JSONResponse(status_code=429, content=envelope("rate_limited", "Too many requests", {"limit_per_minute": settings.rate_limit_per_minute}))
    bucket.append(now)
    started = time.perf_counter()
    response = await call_next(request)
    latency = int((time.perf_counter() - started) * 1000)
    response.headers["x-request-id"] = request_id
    response.headers["x-response-time-ms"] = str(latency)
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["x-frame-options"] = "DENY"
    response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
    log.info("request", method=request.method, status=response.status_code, latency_ms=latency)
    structlog.contextvars.clear_contextvars()
    return response


app.include_router(health_router)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def root():
    return {"app": settings.app_name, "docs": f"{settings.api_prefix}/docs", "health": "/health"}
