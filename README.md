# ESG Nexus

**Enterprise ESG Intelligence, Governance & Reporting Platform**

ESG Nexus is an ESG *system of record*. It manages the lifecycle

`Data → Validation → Calculation → Evidence → Governance → Standards Mapping → Analysis → Evaluation → Assurance → Visualization → Report Generation`

for multi-entity groups. Deterministic engines compute every number; AI agents classify, map, explain and draft; every AI output passes guardrails → evaluation → governance rules → human review before it can become a disclosure; every value resolves to its formula, inputs, source dataset and page-level evidence; and every action is written to an append-only audit trail.

The repository ships a complete backend (FastAPI, SQLAlchemy 2.0, 45 tables, 7 deterministic engines, 10 AI agents, a Mixture-of-Experts copilot, BM25 RAG, governance-as-code, a 9-check report builder with PDF/DOCX/XLSX/CSV/HTML renderers) together with a reference dataset and a React frontend (see [Frontend](#frontend)).

> ESG Nexus reports **framework alignment, disclosure coverage, evidence coverage and reporting readiness**. It never states that an organisation is "compliant" with a standard, and it never fabricates ESG data.

---

## Reference dataset

The seeded tenant models the **Engro Corporation Limited Sustainability Report 2023** (public PDF, 80 PDF pages, reporting period 1 Jan–31 Dec 2023, aligned with the WEF Stakeholder Capitalism Core Metrics, UN Global Compact and UN SDGs, ISAE 3000 limited assurance on selected metrics).

| Aspect | Value |
|---|---|
| Metric definitions | 479 (87 environment, 232 social, 50 governance, 110 prosperity); 58 with formulas; 64 KPIs |
| Numeric metric values | 633 across FY2022/FY2023 (a few FY2021) |
| Narrative (text) values | 66 |
| Entities | 25 (group → subsidiaries / JVs / associates → plants / business units / foundations) |
| Evidence | one `EV-RPT23-P<page>` item per cited printed page, plus 8 non-page items (assurance statement, policies, external studies) |
| Page mapping | printed page *p* is on PDF page `(p + 5) // 2` (`seed/loader.py::printed_to_pdf_page`) |
| Frameworks | WEF_SCM (21 requirements), UNGC (10), UN_SDG (17), GRI (41), IFRS_S (14), ESRS (19), SASB_CHEM (9) |
| Governance rules | 15 rules (GR-001…GR-024, non-contiguous) and 6 policies |

The dataset is deliberately *honest about the source*. Report-internal inconsistencies are stored as reported and surfaced by the data-quality engine instead of being corrected — for example EFERT waste 257 + 1,694 = 1,951 t versus the printed 1,949 t; water consumed entity values sum to 28,775 ML versus the printed 28,776 ML; contractor TRIR recomputes to 0.0946 versus the printed 0.09. Gaps are recorded as gaps: Scope 3 (`ENV.GHG.SCOPE3`) has no value ("Data unavailable"), the CEO pay ratio is an approved omission (confidentiality, WEF index p.151), `ENV.CLIMATE.PARIS_TARGET_SET = 0`, and IFRS S2 financial effects are not available. See [docs/DATA_MODEL_ESG.md](docs/DATA_MODEL_ESG.md).

---

## Architecture

```
                      ┌────────────────────────────────────────────────────────────────┐
  Browser             │  frontend/  React 18 · TypeScript · Vite · Tailwind · Router     │
  :5173 (dev)         │  TanStack Query · Recharts      (nginx :8080 in Docker)          │
  :8080 (docker)      └───────────────────────────┬────────────────────────────────────┘
                                                  │  /api/v1  (JWT bearer)
                      ┌───────────────────────────▼────────────────────────────────────┐
                      │  backend/app/main.py  FastAPI · CORS · rate limit · x-request-id │
                      │  api/v1/*  auth · organizations · esg · metrics · targets ·      │
                      │            calculations · datasets · quality · lineage ·         │
                      │            evidence · frameworks · materiality · governance ·    │
                      │            audit · agents · copilot · knowledge · evaluations ·  │
                      │            reports · admin · health                              │
                      ├──────────────────┬──────────────────────┬───────────────────────┤
                      │ services/        │ engines/  (determin.) │ ai/  (orchestration)   │
                      │ governance_svc   │ safe_expr  metric     │ llm (anthropic|offline)│
                      │ ingestion/       │ consolidation quality │ tools registry (14)    │
                      │ pipeline +       │ lineage rules         │ agents (10) + registry │
                      │ connectors       │ readiness frameworks  │ moe router · rag · … │
                      │ reports/ builder │                       │ guardrails · copilot   │
                      │ + 5 renderers    │                       │                       │
                      ├──────────────────┴──────────────────────┴───────────────────────┤
                      │  models/  45 SQLAlchemy tables · core/ config, security, audit    │
                      └───────────────────────────┬────────────────────────────────────┘
                                                  │
        ┌──────────────────────┬──────────────────┼──────────────────┬──────────────────┐
        │ SQLite (default dev) │ PostgreSQL 16 +  │ Redis (worker    │ MinIO / local    │
        │                      │ pgvector (docker)│ queue, optional) │ storage dir      │
        └──────────────────────┴──────────────────┴──────────────────┴──────────────────┘
        seed/ecorp_2023/*.yaml  (reference dataset)      frameworks/*.yaml (7 standards)
```

Detailed description: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Quick start

### Local (SQLite, offline AI provider)

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt          # Linux/macOS: .venv/bin/pip
.venv/Scripts/uvicorn app.main:app --reload --port 8000
```

On first start the application creates the schema (`Base.metadata.create_all` in `development`/`test`) and seeds the reference tenant (`ESG_AUTO_SEED=true`, ~10 s: metrics, values, evidence, frameworks, knowledge base, then recalculation, quality scoring and rule evaluation for FY2022/FY2023). OpenAPI is served at `http://localhost:8000/api/v1/docs`.

```bash
cd backend && pytest                                    # test-suite (see docs/TESTING.md)

cd frontend && npm install && npm run dev               # http://localhost:5173, proxies /api → :8000
```

### Full stack (Docker Compose)

```bash
cp .env.example .env            # set ESG_SECRET_KEY, optionally ANTHROPIC_API_KEY
docker compose up --build
```

Services: `db` (pgvector/pgvector:pg16), `redis`, `minio`, `backend` (:8000), `worker`, `frontend` (nginx, :8080). See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

### AI provider

| `ESG_AI_PROVIDER` | Behaviour |
|---|---|
| `offline` (default) | `OfflineProvider` — deterministic template narratives built only from the FACTS block the agent supplies. Air-gapped, reproducible, used by the tests. |
| `anthropic` | `AnthropicProvider` — official `anthropic` SDK, model `claude-opus-5` (`ESG_ANTHROPIC_MODEL`), adaptive thinking, `output_config.effort` (`ESG_ANTHROPIC_EFFORT`, default `high`), structured outputs via JSON schema, streaming, prompt caching on the system block. Requires `ANTHROPIC_API_KEY`; if the SDK or key is unavailable the platform logs a warning and degrades to `offline`. |

### Demo accounts

| Email | Password | Roles |
|---|---|---|
| admin@esgnexus.local | Admin!2024 | super_admin, org_admin |
| cso@ecorp.local | Exec!2024 | executive |
| manager@ecorp.local | Manager!2024 | esg_manager |
| analyst@ecorp.local | Analyst!2024 | esg_analyst |
| contributor@ecorp.local | Data!2024 | data_contributor (scoped to entity EFERT) |
| reviewer@ecorp.local | Review!2024 | reviewer |
| approver@ecorp.local | Approve!2024 | report_approver |
| auditor@ecorp.local | Audit!2024 | auditor |

Credentials are seeded from `seed/ecorp_2023/organization.yaml` and are for local evaluation only.

---

## Demo workflow (33 steps)

Each step names the frontend page (left navigation) and the backend endpoint it exercises. All paths are under `/api/v1`.

| # | Step | Page | Endpoint(s) |
|---|---|---|---|
| 1 | Sign in as the ESG Manager | Login | `POST /auth/login` |
| 2 | Review the executive dashboard: 16 KPI cards, readiness gauge, open issues, "what changed" | Dashboard | `GET /esg/overview` |
| 3 | Inspect readiness components and blocking issues | Dashboard → readiness panel | `GET /evaluations/readiness` |
| 4 | Open ESG Intelligence → Environment; drill into GHG Emissions | ESG Intelligence / Environment | `GET /esg/pillar/environment` |
| 5 | Open Scope 1 detail: value, trend, consolidation from entities, evidence pages, quality, governance | Metrics Library → metric detail | `GET /metrics/ENV.GHG.SCOPE1/detail` |
| 6 | Compare Scope 1 across entities (EEL 5,075,867 tCO2e dominates) | ESG Intelligence → entity comparison | `GET /esg/entity-comparison?metric=ENV.GHG.SCOPE1` |
| 7 | Open the lineage graph: metric → calculation → inputs → dataset → source → evidence | Data → Lineage | `GET /lineage?metric=ENV.GHG.SCOPE1_2_TOTAL` |
| 8 | Show the recalculation of employee TRIR (3 × 200,000 ÷ 6,840,000 = 0.0877 ≈ 0.09) | Metrics → Calculations | `POST /metrics/SOC.OHS.TRIR_EMP/calculate?persist=false` |
| 9 | Show the reported-vs-recalculated consistency finding for waste (1,951 vs 1,949) | Data → Data Quality | `GET /quality/scores?metric=ENV.WASTE.TOTAL&entity=EFERT` |
| 10 | Review the data-quality summary and lowest-scoring values | Data → Data Quality | `GET /quality/summary` |
| 11 | Register data sources (SAP, SuccessFactors, VelocityEHS, historians) | Data → Data Sources | `GET /datasets/sources` |
| 12 | Sign in as the Data Contributor and upload a CSV of plant values | Data → Datasets → Upload | `POST /datasets/upload` |
| 13 | Run the ESG Data Agent to classify columns and propose metric mappings | Data → Datasets → Classify | `POST /datasets/classify` |
| 14 | Inspect validation results and invalid rows; load the version | Data → Datasets | `GET /datasets/versions/{id}/records?only_invalid=true`, `POST /datasets/versions/{id}/load` |
| 15 | Enter a manual value with evidence; observe the input guardrail (range check) | Metrics → KPI Tracking | `POST /metrics/{code}/values` |
| 16 | Recalculate all derived metrics for FY2023 (dependency ordered) | Metrics → Calculations | `POST /calculations/recalculate?period=FY2023` |
| 17 | Review targets, including "not set" gaps (no Paris-aligned GHG target) | Metrics → Targets | `GET /targets` |
| 18 | Review framework registry and WEF Core coverage (complete / partial / missing / omitted) | Standards → Frameworks / Compliance | `GET /frameworks`, `GET /frameworks/WEF_SCM/coverage` |
| 19 | Open the CEO pay ratio omission on WEF.PEOPLE.WAGE_LEVEL | Standards → Mapping | `GET /frameworks/requirements/WEF.PEOPLE.WAGE_LEVEL` |
| 20 | Run the Standards Mapping Agent gap analysis for IFRS S2 | Standards → Requirements | `POST /frameworks/gap-analysis?framework=IFRS_S` |
| 21 | Open the materiality matrix; adjust a topic score and see the material flag recalculated | Materiality → Matrix | `GET /materiality/assessments/{id}`, `PUT /materiality/assessments/{id}/topics/{topic}` |
| 22 | Review evidence gaps and unverified evidence | Evidence → Gaps | `GET /evidence/gaps` |
| 23 | Sign in as the Auditor and verify the ISAE 3000 assurance statement evidence | Evidence → Repository | `POST /evidence/EV-ISAE3000-2023/verify` |
| 24 | Ask the Copilot "Why did our Scope 1 emissions increase in FY2023?" and inspect route, sources, confidence | AI → Copilot | `POST /copilot/ask` |
| 25 | Ask "What is preventing report publication?" (routes to the Risk expert / Assurance Agent) | AI → Copilot | `POST /copilot/ask` |
| 26 | Open the agent run: tools used, guardrails, evaluation scores, governance outcomes, model runs | AI → Agent Runs | `GET /agents/runs/{id}` |
| 27 | Search the knowledge base with permission filtering (policies hidden from the contributor) | AI → Knowledge Base / RAG | `POST /knowledge/search` |
| 28 | Review governance rules and test a condition against a context | Governance → Rules | `GET /governance/rules`, `POST /governance/rules/test` |
| 29 | Review open issues by severity; acknowledge one; approve a documented exception | Governance → Approvals | `GET /governance/issues`, `POST /governance/issues/{code}/exception` |
| 30 | Create the FY2023 annual report and generate the AI draft (sections drafted, evaluated, gated) | Reports → Builder | `POST /reports`, `POST /reports/{id}/generate-draft` |
| 31 | Run the nine pre-generation checks; observe the explicit block reasons | Reports → Builder → Validate | `POST /reports/{id}/validate` |
| 32 | Review and approve sections as the Reviewer/Approver, then approve the report (data freezes, GR-020) | Reports → Preview | `PUT /reports/{id}/sections/{code}`, `POST /reports/{id}/transition` |
| 33 | Generate the final PDF and DOCX, download, and open the audit trail for the whole session | Reports → Generated / Governance → Audit Trail | `POST /reports/{id}/generate?format=pdf&final=true`, `GET /audit` |

---

## Repository layout

```
esg-nexus/
├── README.md                     this file
├── .env.example                  environment template (ESG_* variables)
├── docker-compose.yml            db (pgvector) · redis · minio · backend · worker · frontend
├── deploy/postgres/init.sql      CREATE EXTENSION vector
├── frameworks/*.yaml             configuration-driven standards (WEF_SCM, UNGC, UN_SDG, GRI, IFRS_S, ESRS, SASB_CHEM)
├── seed/ecorp_2023/              reference dataset (organization, topics, metrics_*, evidence, targets,
│                                 materiality, governance, data_sources, report_pages.json)
├── backend/
│   ├── Dockerfile · requirements.txt · pyproject.toml · alembic.ini
│   ├── alembic/                  env.py wired to app settings + metadata (no revisions shipped yet)
│   ├── tests/                    pytest suite (46 tests: engines, golden calculations, governance, AI evals, API workflow)
│   └── app/
│       ├── main.py               app factory, middleware, routers, lifespan (create_all + seed)
│       ├── worker.py             background worker (Redis list queue or 6-hourly loop)
│       ├── core/                 config · db · security (JWT, PBKDF2, RBAC) · errors · logging · audit
│       ├── models/               45 tables in 11 modules
│       ├── api/v1/               12 router modules, 20 routers
│       ├── engines/              safe_expr · metric_engine · consolidation · data_quality · lineage · rules · readiness · frameworks
│       ├── ai/                   llm/ · tools/ · agents/ · rag/ · moe/ · guardrails/ · copilot.py
│       ├── ingestion/            connectors (csv, json, excel, pdf, text) · pipeline
│       ├── reports/              templates/*.yaml · builder.py · renderers/ (pdf, docx, xlsx, csv, html)
│       ├── services/             governance_service.py
│       └── seed/                 loader.py (idempotent Seeder)
├── frontend/                     React SPA (nginx image on :8080)
└── docs/                         documentation set (index below)
```

---

## Documentation index

| Document | Content |
|---|---|
| [docs/BLUEPRINT.md](docs/BLUEPRINT.md) | The pre-implementation design (sections A–W) every module implements |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System and domain architecture, bounded contexts, request flow, engines, AI layer, extensibility, life of a metric value |
| [docs/DATABASE.md](docs/DATABASE.md) | ERD, table-by-table description, constraints, tenant isolation, Alembic |
| [docs/API.md](docs/API.md) | Every endpoint with capability, purpose, parameters, examples, error envelope, pagination |
| [docs/AGENTS.md](docs/AGENTS.md) | Agent pipeline, the 10 agents, controlled tools, MoE router, Copilot, providers, thresholds |
| [docs/RAG.md](docs/RAG.md) | Knowledge documents, chunking, BM25 index, permission filtering, reranking, citations, pgvector |
| [docs/GOVERNANCE.md](docs/GOVERNANCE.md) | Governance-as-code schema, condition DSL, actions, seeded rules, issues, approvals, readiness, audit |
| [docs/SECURITY.md](docs/SECURITY.md) | Auth, RBAC matrix, tenant isolation, scoping, rate limiting, headers, guardrails, hardening |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Compose services, env vars, PostgreSQL/pgvector, migrations, health, Kubernetes, air-gapped, backups, observability |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | Developer setup, code map, conventions, tests, adding an endpoint |
| [docs/TESTING.md](docs/TESTING.md) | Test layers, golden calculations, AI eval suite |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Evaluation centre dimensions and formulas |
| [docs/FRAMEWORKS.md](docs/FRAMEWORKS.md) | Framework YAML schema, the 7 frameworks, coverage/alignment computation, omissions |
| [docs/DATA_MODEL_ESG.md](docs/DATA_MODEL_ESG.md) | ESG ontology, metric definition fields, seed YAML format, consolidation, evidence, targets, materiality |
| [docs/guides/add-metric.md](docs/guides/add-metric.md) | Add a metric (raw or derived) |
| [docs/guides/add-framework.md](docs/guides/add-framework.md) | Add a framework YAML |
| [docs/guides/add-agent.md](docs/guides/add-agent.md) | Add an agent and register it |
| [docs/guides/add-report-section.md](docs/guides/add-report-section.md) | Add a report template section |
| [docs/guides/add-connector.md](docs/guides/add-connector.md) | Add an ingestion connector |
| [docs/guides/add-governance-rule.md](docs/guides/add-governance-rule.md) | Add a governance rule |

---

## Principles

1. **No fabricated ESG data.** Missing values are returned as `Data unavailable`, `Evidence required` or `Human review required`; the offline provider and the agent system prompt (`ai/agents/base.py::BASE_SYSTEM`) forbid invention; the output guardrail blocks narratives containing numbers that are not governed metric values.
2. **Alignment, not compliance.** Framework results are *alignment %*, *disclosure coverage* and *gaps*, always accompanied by a disclaimer; the output guardrail flags "compliant with GRI/IFRS/…" phrasing.
3. **Deterministic engines compute; AI explains and drafts.** The Calculation Agent calls `calculate_metric`; it never computes. Formulas are versioned (`calculation_versions`) and every execution is a `calculation_run`.
4. **Facts-first agents.** Agents obtain facts only through the controlled tool registry (tenant- and entity-scoped); the model receives a FACTS block and composes.
5. **Guardrails → evaluation → governance → human review.** Every agent run records guardrail results, evaluation scores, triggered governance rules and whether human review is required.
6. **Immutable audit trail.** `core/audit.py` exposes only an append operation; no update or delete API exists for `audit_logs`.
7. **Configuration over code.** Frameworks, report templates, governance rules, metric catalogues and seed data are YAML/JSON; new agents, tools, connectors, renderers and providers register through registries.

---

## Frontend

The frontend (`frontend/`) is being built concurrently and is described here from its plan. Stack: React 18, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, Recharts. Development server on `http://localhost:5173` proxying `/api` to `http://localhost:8000`; the Docker image is served by nginx on port 8080 (`VITE_API_BASE=/api/v1`).

Left navigation :

- **Dashboard**
- **ESG Intelligence** — Overview · Environment · Social · Governance · Prosperity
- **Data** — Data Sources · Datasets · Data Quality · Lineage
- **Metrics** — Library · KPI Tracking · Calculations · Targets
- **Standards** — Frameworks · Requirements · Mapping · Compliance (alignment and gaps; the page reports alignment, not compliance status)
- **Materiality** — Assessment · Matrix
- **Evidence** — Repository · Gaps
- **AI** — Agents · Agent Runs · Knowledge Base · RAG · Evaluation · Copilot
- **Governance** — Policies · Rules · Approvals · Audit Trail
- **Reports** — Builder · Preview · Generated
- **Administration** — Organization · Users · Roles · System

---

## Status and known limits

- **Vector search is an extension point.** Retrieval is in-process BM25 (`ai/rag/index.py::LexicalIndex`). `PgVectorIndex` exists as an adapter but no embedding provider is implemented (`ESG_EMBEDDING_PROVIDER` accepts `none|voyage`; only `none` is wired). `knowledge_chunks.embedding` is a JSON column; migrating it to a native `vector` column is described in [docs/RAG.md](docs/RAG.md).
- **The worker is a lightweight queue.** `app/worker.py` pops JSON jobs from the Redis list `esg:jobs` when `ESG_REDIS_URL` is set (falling back to an in-process 6-hourly recompute loop); only the `recompute` job is registered. Replace with Celery/RQ for production scheduling.
- **Migrations.** The initial Alembic revision is shipped (`backend/alembic/versions/`); `development`/`test` additionally create tables at startup so a fresh SQLite file works without running Alembic (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).
- **Object storage is configured but not used by code.** Report files and uploaded evidence are written under `ESG_LOCAL_STORAGE_DIR` (a Docker volume in Compose). The MinIO service and `ESG_OBJECT_STORAGE_*` settings are provisioned for a future storage adapter.
- **Rate limiting is per process.** The middleware keeps in-memory per-IP buckets; with `--workers 2` each worker counts independently. Put a gateway limiter in front for production.
- **Dataset- and evidence-level `permissions` JSON columns are stored but not enforced**; only knowledge-document permissions are enforced (permission-aware RAG). Entity scoping of principals *is* enforced on entity lookups and tools.
- Report generation writes files synchronously in the request; long AI drafts with the Anthropic provider are streamed but still executed inline (no job offloading yet).

---

## Licence and data

Source code in this repository is provided for the ESG Nexus platform. The reference data is derived from a publicly available sustainability report and is used solely to demonstrate evidence-backed ESG data management; no statement in this repository constitutes an assurance conclusion or a compliance opinion.
