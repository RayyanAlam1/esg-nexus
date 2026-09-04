# Developer Onboarding

Related: [ARCHITECTURE.md](ARCHITECTURE.md) · [API.md](API.md) · [TESTING.md](TESTING.md) · [guides/](guides/).

---

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 (image uses 3.12) | `backend/pyproject.toml` `requires-python = ">=3.11"` |
| Node.js | 18+ | Frontend (Vite) |
| Docker + Compose | recent | Full stack |
| PostgreSQL 16 | optional | SQLite is the local default |

---

## 2. Backend setup

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt          # Windows; use .venv/bin/pip elsewhere
.venv/Scripts/uvicorn app.main:app --reload --port 8000
```

First start: schema via `create_all` (development), then the seeder loads `seed/ecorp_2023` and `frameworks/` (~10 s). Open `http://localhost:8000/api/v1/docs`, log in with `manager@ecorp.local / Manager!2024` (see [README](../README.md#demo-accounts)) and authorise Swagger with the access token.

Optional `.env` at the repository root (copy `.env.example`). Useful local overrides:

```
ESG_DATABASE_URL=sqlite:///./backend/esg_nexus.db
ESG_AI_PROVIDER=offline
ESG_LOG_LEVEL=DEBUG
```

To reseed from scratch: stop the server, delete `backend/esg_nexus.db`, start again — or call `POST /admin/reseed` as `admin@esgnexus.local`.

## 3. Frontend setup

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173, /api proxied to http://localhost:8000
```

The frontend is a standalone Vite project (React 18, TypeScript, Vite, Tailwind, React Router, TanStack Query, Recharts). Its production build is served by nginx on port 8080 in Compose.

---

## 4. Code map

```
backend/app/
  main.py            FastAPI app, middleware (request id, rate limit, headers, access log), routers, lifespan
  worker.py          background jobs (JOBS registry)
  core/
    config.py        Settings (ESG_* env vars)               security.py  roles, capabilities, JWT, PBKDF2, Principal
    db.py            engine, SessionLocal, Base, mixins       errors.py    AppError hierarchy + envelope
    logging.py       structlog                                audit.py     append-only audit writer
  models/            identity, organization, esg, data, evidence, frameworks, materiality, governance, ai, reporting, audit
  api/
    deps.py          DB/User dependencies, Page, serialize, paginate, get_org/get_period/get_entity/get_metric
    v1/              auth, organizations, esg, metrics (+targets, calculations), datasets (+quality, lineage),
                     evidence, frameworks, materiality, governance (+audit), agents (+copilot, knowledge, evaluations),
                     reports, admin (+health)
  engines/           safe_expr, metric_engine, consolidation, data_quality, lineage, rules, readiness, frameworks
  ai/
    llm/             base (protocol, registry), anthropic_provider, offline_provider
    tools/registry.py   @tool functions + ToolContext
    agents/          base (pipeline), specialists (10 agents), registry, evaluation (scoring)
    rag/             index (BM25, PgVector adapter), retriever
    moe/             experts + classify + aggregate
    guardrails/      input/output guardrails
    copilot.py       ask()
  ingestion/         connectors (@connector), pipeline
  reports/           templates/*.yaml, builder.py, renderers/{pdf,docx,xlsx,csv,html}_renderer.py, markdown_util.py
  services/governance_service.py
  seed/loader.py     Seeder, seed_if_needed
frameworks/*.yaml    framework definitions
seed/ecorp_2023/     reference dataset
docs/                this documentation
```

Where to look for a behaviour:

| Question | File |
|---|---|
| How is a formula evaluated? | `engines/safe_expr.py` (`compile_formula`, `evaluate`), `engines/metric_engine.py::calculate` |
| Why does a group value differ from the printed total? | `engines/consolidation.py::aggregate` (factors), metric `notes` in seed YAML |
| Why is a quality score low? | `engines/data_quality.py::assess` — every deduction appends to `explanation` |
| Why is a report blocked? | `reports/builder.py::validate` (nine checks), `services/governance_service.py::check_report` |
| Which rule raised an issue? | `issues.rule_code`, `engines/rules.py`, `seed/ecorp_2023/governance.yaml` |
| What did an agent do? | `agent_runs` row (`tools_used`, `guardrail_result`, `evaluation_id`), `ai/agents/base.py::run` |
| How is a route protected? | `require("<capability>")` in the router, `core/security.py::CAPABILITIES` |

---

## 5. Conventions

- **Style**: `ruff` configuration in `pyproject.toml` (line length 180, target py311); `from __future__ import annotations`; type hints on public functions; module docstrings describing the responsibility and the blueprint reference (e.g. "", "").
- **Layering**: routers call engines/services and commit; engines never commit (they `flush`) and never import the AI layer; agents access data only through tools.
- **Transactions**: one session per request (`deps.DB`); handlers call `db.commit()` after `audit.record(...)`. Services and engines `flush()` so ids are available.
- **Errors**: raise `AppError` subclasses from `core/errors.py`; never return ad-hoc error dictionaries (the only exceptions are tool results inside agents, which return `{"error": …}` so a failing tool is visible in the facts).
- **Audit**: every state-changing endpoint records an audit entry with `object_type`, `object_id`, old/new values and an optional `reason`.
- **Tenant scoping**: always filter by `principal.tenant_id`; use the `deps.get_*` helpers.
- **Serialisation**: return `serialize(model)` dictionaries or explicit dicts; never ORM objects.
- **No fabricated data**: engines return `None`/`Data unavailable`; never default a missing ESG value to zero except through the explicit `nz()` helper in a formula, with a description explaining why.
- **Language**: framework results are "alignment"/"coverage"; avoid "compliant" in code, prompts and UI strings.
- **Configuration first**: prefer adding YAML (frameworks, templates, rules, metrics) over code; register new components in the appropriate registry.

---

## 6. Running tests

```bash
cd backend
pytest              # pyproject: testpaths = ["tests"], addopts = "-q"
```

Tests use the offline provider and a SQLite database; see [TESTING.md](TESTING.md) for the layers, fixtures and golden calculations.

---

## 7. Adding an endpoint

1. **Choose the router** in `app/api/v1/` (or create a module and add its `APIRouter` to the list in `app/api/v1/__init__.py`).
2. **Define request/response models** with Pydantic in the router module (`class ThingIn(BaseModel)`).
3. **Protect it**: `dependencies=[Depends(require("metric.write"))]` for a capability, `principal: User` for the caller, `db: DB` for the session. Add a new capability to `core/security.py::CAPABILITIES` if none fits (additive change; update [SECURITY.md](SECURITY.md#2-rbac-matrix)).
4. **Resolve scope** with `get_org / get_period / get_entity / get_metric` from `app/api/deps.py` — these enforce tenant and entity scoping and raise 404/403.
5. **Call an engine or service**; do not put domain logic in the router.
6. **Audit and commit**: `audit.record(db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="thing.create", object_type="thing", object_id=obj.id, new_value=body.model_dump())` then `db.commit()`.
7. **Return** `serialize(obj)` or `paginate(db, stmt, page, Model)` for lists (`page: Page = Depends()`).
8. **Test** with `TestClient` (see [TESTING.md](TESTING.md#34-api-tests-teststest_api_py)) and document the endpoint in [API.md](API.md).

Example skeleton:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.api.deps import DB, User, get_metric, serialize
from app.core import audit
from app.core.security import require

router = APIRouter(prefix="/things", tags=["things"])

class ThingIn(BaseModel):
    metric_code: str
    note: str | None = None

@router.post("", dependencies=[Depends(require("metric.write"))])
def create_thing(body: ThingIn, principal: User, db: DB):
    metric = get_metric(db, principal, body.metric_code)          # tenant-scoped, 404 on miss
    obj = ...                                                      # engine/service call
    audit.record(db, tenant_id=principal.tenant_id, user_id=principal.user_id, action="thing.create",
                 object_type="thing", object_id=obj.id, new_value=body.model_dump())
    db.commit()
    return serialize(obj)
```

Register the router in `app/api/v1/__init__.py`:

```python
from app.api.v1 import things
for r in [..., things.router]:
    api_router.include_router(r)
```

---

## 8. Useful commands

| Task | Command |
|---|---|
| OpenAPI JSON | `curl localhost:8000/api/v1/openapi.json` |
| Login and store token (bash) | `T=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'content-type: application/json' -d '{"email":"manager@ecorp.local","password":"Manager!2024"}' \| python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")` |
| Reload frameworks after editing YAML | `curl -X POST localhost:8000/api/v1/frameworks/reload -H "authorization: Bearer $T"` |
| Recalculate FY2023 | `curl -X POST "localhost:8000/api/v1/calculations/recalculate?period=FY2023" -H "authorization: Bearer $T"` |
| Full stack | `docker compose up --build` |
| Alembic revision | `cd backend && alembic revision --autogenerate -m "…"` |
