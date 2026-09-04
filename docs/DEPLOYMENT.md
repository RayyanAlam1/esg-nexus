# Deployment

ESG Nexus ships a Docker image for the backend (API and worker share it), a Compose stack for the full platform, and 12-factor configuration so the same image runs in Kubernetes or on an air-gapped host.

Related: [SECURITY.md](SECURITY.md#10-deployment-hardening-checklist) · [DATABASE.md](DATABASE.md#6-migrations-alembic) · [RAG.md](RAG.md#7-enabling-pgvector).

---

## 1. Docker Compose (`docker-compose.yml`)

```bash
cp .env.example .env         # edit secrets
docker compose up --build    # http://localhost:8080 (frontend), http://localhost:8000/api/v1/docs (API)
```

| Service | Image / build | Ports | Purpose | Health check |
|---|---|---|---|---|
| `db` | `pgvector/pgvector:pg16` | 5432 | PostgreSQL 16 with the `vector` extension (`deploy/postgres/init.sql` runs `CREATE EXTENSION IF NOT EXISTS vector` on first init); volume `pgdata` | `pg_isready -U esg -d esg_nexus` |
| `redis` | `redis:7-alpine` (AOF) | — | Job queue for the worker (list `esg:jobs`); volume `redisdata` | `redis-cli ping` |
| `minio` | `minio/minio:latest` | 9000 (S3), 9001 (console) | S3-compatible object store; volume `miniodata`. Provisioned for a storage adapter — the current code writes files to the local storage volume. | `mc ready local` |
| `backend` | `backend/Dockerfile` (context `.`) | 8000 | API; `alembic upgrade head` then `uvicorn app.main:app --workers ${WEB_CONCURRENCY:-2}`; volume `storage:/data/storage` | Dockerfile `HEALTHCHECK` on `/health/ready` |
| `worker` | same image, `python -m app.worker` | — | Background recompute (see §6); `ESG_AUTO_SEED=false` | — |
| `frontend` | `./frontend` (nginx) | 8080 → 80 | React SPA, `VITE_API_BASE=/api/v1`; nginx proxies `/api` to `backend:8000` | — |

Start-up order: `backend` waits for `db` and `redis` to be healthy; `worker` waits for `backend` to start; `frontend` depends on `backend`.

The backend image (`python:3.12-slim`) copies `backend/` to `/app`, `frameworks/` to `/frameworks`, `seed/` to `/seed`, installs `requirements.txt`, creates the non-root user `esg`, and sets `ESG_FRAMEWORKS_DIR=/frameworks`, `ESG_SEED_DIR=/seed/ecorp_2023`, `ESG_LOCAL_STORAGE_DIR=/data/storage`.

---

## 2. Environment variables (`app/core/config.py`)

All settings use the prefix `ESG_` and are read from the environment, then `<repo>/.env`, then `backend/.env`. Lists (e.g. CORS origins) are JSON-encoded.

| Variable | Default | Description |
|---|---|---|
| `ESG_APP_NAME` | `ESG Nexus` | Display name |
| `ESG_ENVIRONMENT` | `development` | `development | test | staging | production`. `create_all` runs only in development/test. |
| `ESG_DEBUG` | `false` | Debug flag |
| `ESG_API_PREFIX` | `/api/v1` | Route prefix for the API, docs and OpenAPI |
| `ESG_DATABASE_URL` | `sqlite:///<backend>/esg_nexus.db` | SQLAlchemy URL; Compose uses `postgresql+psycopg://esg:<pw>@db:5432/esg_nexus` |
| `ESG_REDIS_URL` | unset | Enables the Redis queue in the worker (`redis://redis:6379/0`) |
| `ESG_OBJECT_STORAGE_ENDPOINT` | unset | S3 endpoint (reserved) |
| `ESG_OBJECT_STORAGE_BUCKET` | `esg-nexus` | Bucket name (reserved) |
| `ESG_OBJECT_STORAGE_ACCESS_KEY` / `ESG_OBJECT_STORAGE_SECRET_KEY` | unset | S3 credentials (reserved) |
| `ESG_LOCAL_STORAGE_DIR` | `<backend>/storage` | Where report files (`reports/<id>/…`) and uploaded evidence (`evidence/…`) are written |
| `ESG_SECRET_KEY` | `change-me-in-production` | JWT signing key — override in every non-development deployment |
| `ESG_ACCESS_TOKEN_MINUTES` | `480` | Access-token lifetime |
| `ESG_REFRESH_TOKEN_DAYS` | `14` | Refresh-token lifetime |
| `ESG_CORS_ORIGINS` | `["http://localhost:5173","http://localhost:3000","http://localhost:8080"]` | Allowed origins |
| `ESG_RATE_LIMIT_PER_MINUTE` | `600` | Per-IP, per-process request limit |
| `ESG_AI_PROVIDER` | `offline` | `offline | anthropic` |
| `ESG_ANTHROPIC_MODEL` | `claude-opus-5` | Model id for the Anthropic provider |
| `ESG_ANTHROPIC_EFFORT` | `high` | `low | medium | high | xhigh | max` → `output_config.effort` |
| `ESG_ANTHROPIC_MAX_TOKENS` | `16000` | Max output tokens per call |
| `ANTHROPIC_API_KEY` | unset | Read directly by the Anthropic SDK (no `ESG_` prefix) |
| `ESG_AI_CONFIDENCE_THRESHOLD` | `0.75` | Below this, agent outputs require human review |
| `ESG_EMBEDDING_PROVIDER` | `none` | `none | voyage` (only `none` is implemented) |
| `ESG_FRAMEWORKS_DIR` | `<repo>/frameworks` | Framework YAML directory |
| `ESG_SEED_DIR` | `<repo>/seed/ecorp_2023` | Reference dataset directory |
| `ESG_SOURCE_PDF_PATH` | `<repo parent>/ECORP-Sustainability-Report-01-07-24.pdf` | Location of the source PDF (informational; page text is pre-extracted in `report_pages.json`) |
| `ESG_AUTO_SEED` | `true` | Seed the reference tenant at start-up when missing |
| `ESG_LOG_LEVEL` | `INFO` | Log level |
| `ESG_JSON_LOGS` | `false` | JSON log rendering (Compose sets `true`) |

Compose-only variables (`.env`): `POSTGRES_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `WEB_CONCURRENCY` (uvicorn workers, default 2).

---

## 3. Database

### PostgreSQL / pgvector

Use `pgvector/pgvector:pg16` (or install the `vector` extension on a managed PostgreSQL 16). The application only needs the extension once embeddings are enabled ([RAG.md](RAG.md#7-enabling-pgvector)); without it the schema still works because `knowledge_chunks.embedding` is a JSON column. Driver: `psycopg` 3 (`psycopg[binary]`).

### Migrations

`alembic/env.py` reads the URL from settings and targets `Base.metadata`. The initial revision (`backend/alembic/versions/20260904_5f7f01feec2c_initial_schema.py`, all 45 tables) is shipped and baked into the image:

- `development` / `test`: the lifespan hook additionally runs `Base.metadata.create_all(engine)` so a fresh SQLite file works without Alembic.
- `staging` / `production`: the Docker `CMD` runs `alembic upgrade head` before starting the API.

```bash
docker compose run --rm backend alembic upgrade head                                  # apply
docker compose run --rm backend alembic revision --autogenerate -m "describe change"  # after model changes (copy the file back into backend/alembic/versions)
```

### SQLite (local)

Default for local development and tests: single file `backend/esg_nexus.db`, WAL journal, foreign keys enabled by a connect hook. Delete the file to reseed from scratch. Not suitable for multi-process production use.

---

## 4. Health checks and probes

| Endpoint | Use |
|---|---|
| `GET /health` | Liveness — process is up (`status`, `app`, `uptime_seconds`) |
| `GET /health/ready` | Readiness — `SELECT 1` succeeds and tenants are counted; returns `seeded: true|false`; `status: degraded` with the error otherwise (HTTP 200 in both cases — check the JSON `status`) |

The Dockerfile `HEALTHCHECK` polls `/health/ready` every 30 s (timeout 5 s, 5 retries).

---

## 5. Kubernetes readiness

- **Stateless API pods.** No session state; JWTs are self-contained. Two in-memory structures exist per process — the rate-limit buckets and the per-tenant BM25 index cache — both are safe to lose on restart.
- **Probes.** `livenessProbe: GET /health`, `readinessProbe: GET /health/ready` (treat `"status":"ready"` as success; a startup probe with a generous window is advisable because the first start seeds the reference tenant, ~10 s on SQLite, longer on PostgreSQL).
- **Configuration.** ConfigMap for non-secret `ESG_*` values; Secrets for `ESG_SECRET_KEY`, database URL, `ANTHROPIC_API_KEY`, object-storage keys.
- **Storage.** Mount a ReadWriteMany volume (or run a single replica) at `ESG_LOCAL_STORAGE_DIR` until an object-storage adapter is implemented; the MinIO service is available for that adapter.
- **Migrations.** Run `alembic upgrade head` as a Job or init container before rolling the API; set `ESG_ENVIRONMENT=production` so pods do not call `create_all`.
- **Seeding.** Run the seed once (first API start with `ESG_AUTO_SEED=true`, or `POST /admin/reseed` as super_admin), then set `ESG_AUTO_SEED=false`.
- **Worker.** Deploy `python -m app.worker` as a separate Deployment (one replica is sufficient) with `ESG_REDIS_URL` set; enqueue jobs with `LPUSH esg:jobs '{"job":"recompute","kwargs":{"period_code":"FY2023"}}'`.
- **Scaling.** Horizontal scaling of the API is straightforward; rate limiting should move to the ingress.
- **Ingress.** TLS termination, HSTS, CSP, request size limits, forwarding of `X-Forwarded-For` and `x-request-id`.

---

## 6. Background worker (`app/worker.py`)

| Mode | Condition | Behaviour |
|---|---|---|
| Queue | `ESG_REDIS_URL` set **and** the `redis` package importable | `BLPOP esg:jobs` (30 s timeout); payload `{"job": "<name>", "kwargs": {...}}`; jobs from `JOBS` (`recompute`) |
| Scheduled | otherwise | `job_recompute()` for every tenant/organisation/period every 6 hours |

`job_recompute(period_code=None)` runs `recalculate_all`, `assess_all` and `run_metric_rules` per period and commits. Note: `redis` is not in `requirements.txt`; add it to enable queue mode in the image.

---

## 7. On-premise and air-gapped mode

- `ESG_AI_PROVIDER=offline` uses `OfflineProvider` — deterministic, no network calls; all agents, the Copilot and report drafting work with template narratives derived from governed facts.
- `ESG_EMBEDDING_PROVIDER=none` keeps retrieval on the in-process BM25 index.
- The `anthropic` package is installed but only imported lazily when the provider is `anthropic`; if it cannot be constructed the platform logs a warning and falls back to offline.
- No other outbound calls exist: frameworks, seed data and page text are files in the image; fonts for PDF generation are reportlab's built-in Helvetica.
- Tenants may record `deployment_model` (`saas | private_cloud | on_prem | air_gapped`) for documentation purposes.

---

## 8. Backups

| Data | Location | Note |
|---|---|---|
| Relational data (all 45 tables, including audit logs, agent/model runs, evaluations) | PostgreSQL volume `pgdata` (or `backend/esg_nexus.db`) | `pg_dump` on a schedule; audit logs are append-only and should be retained per policy |
| Generated reports and uploaded evidence | volume `storage` (`ESG_LOCAL_STORAGE_DIR/reports/<report_id>/…`, `…/evidence/…`) | `report_versions.storage_key` and `evidence.storage_key` hold absolute paths; back up together with the database so hashes and paths stay consistent |
| Redis | volume `redisdata` | Queue only; safe to lose |
| Configuration | `.env`, framework YAML, seed YAML | Version-controlled except `.env` |

Restore order: database, then storage volume, then start the API with `ESG_AUTO_SEED=false`.

---

## 9. Observability

| Signal | Source |
|---|---|
| Structured logs | `structlog` (`core/logging.py`): console renderer in development, JSON when `ESG_JSON_LOGS=true`; every request logs `method, status, latency_ms, request_id, path` |
| Correlation | `x-request-id` request/response header, bound into log context for the duration of the request |
| Latency | `x-response-time-ms` response header |
| AI usage | `model_runs` (provider, model, purpose, prompt/completion/cache-read tokens, latency, status, error) and `agent_runs` (status, confidence, latency, guardrail results); aggregated by `GET /evaluations/summary → observability` |
| Platform stats | `GET /admin/system` (environment, database backend, provider, counts, uptime, config) |
| Audit | `GET /audit` |
| Errors | Uniform JSON envelope; 5xx are logged with stack info by structlog |

Metrics endpoints (Prometheus) are not implemented; logs and the tables above are the integration points for an external collector.
