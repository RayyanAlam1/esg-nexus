# Architecture

This document describes the implemented architecture of ESG Nexus. It follows the design in [BLUEPRINT.md](BLUEPRINT.md) (sections E–L, Q, W) and references concrete modules under `backend/app/`.

Related: [DATABASE.md](DATABASE.md) · [API.md](API.md) · [AGENTS.md](AGENTS.md) · [RAG.md](RAG.md) · [GOVERNANCE.md](GOVERNANCE.md) · [SECURITY.md](SECURITY.md) · [DEPLOYMENT.md](DEPLOYMENT.md).

---

## 1. System overview

```
React SPA (frontend/) ──HTTP /api/v1──► FastAPI (backend/app/main.py)
                                          │
                     ┌────────────────────┼─────────────────────┐
                     ▼                    ▼                     ▼
              api/v1 routers        engines/ (pure,         ai/ (orchestration:
              + api/deps            deterministic)          providers, tools, agents,
                     │                    │                 MoE, RAG, guardrails)
                     ▼                    │                     │
              services/ · ingestion/ · reports/ (application logic)
                     │                    │                     │
                     └────────────────────┼─────────────────────┘
                                          ▼
                              models/ (SQLAlchemy 2.0, 45 tables)
                                          ▼
                    SQLite (dev/test)  |  PostgreSQL 16 + pgvector (docker/prod)
```

Layering (Clean Architecture, blueprint §E):

| Layer | Location | Responsibility |
|---|---|---|
| Transport | `app/api/v1/*.py`, `app/api/deps.py` | Pydantic request models, RBAC dependencies, serialisation, pagination, commit boundaries |
| Application | `app/services/governance_service.py`, `app/ingestion/pipeline.py`, `app/reports/builder.py`, `app/ai/copilot.py`, `app/seed/loader.py` | Use-case orchestration across engines, models and AI |
| Domain (deterministic) | `app/engines/*` | Formula evaluation, consolidation, quality, lineage, rules, readiness, framework coverage |
| Domain (AI) | `app/ai/*` | Provider abstraction, controlled tools, agents, evaluation, guardrails, MoE routing, RAG |
| Persistence | `app/models/*`, `app/core/db.py` | Tables, mixins (`PKMixin`, `TimestampMixin`, `TenantMixin`), session factory |
| Cross-cutting | `app/core/{config,security,errors,logging,audit}.py` | Settings, JWT/RBAC, error envelope, structlog, audit writer |

Configuration is 12-factor (`app/core/config.py::Settings`, env prefix `ESG_`, `.env` read from the repository root or `backend/`).

---

## 2. Bounded contexts

The blueprint names fourteen bounded contexts. The table maps each to its models, engines/services and routers.

| Context | Models (`app/models/`) | Logic | Routers (`app/api/v1/`) |
|---|---|---|---|
| Identity & tenancy | `identity.py`: Tenant, User, Role, UserRole | `core/security.py` | `auth.py`, `admin.py` |
| Organization | `organization.py`: Organization, Entity, ReportingPeriod | `engines/consolidation.py::tree` | `organizations.py` |
| ESG data & metrics | `esg.py`: EsgTopic, EsgSubtopic, MetricDefinition, MetricValue, Target, CalculationVersion, CalculationRun | `engines/metric_engine.py`, `engines/consolidation.py`, `engines/safe_expr.py` | `esg.py`, `metrics.py` (metrics, targets, calculations) |
| Data ingestion | `data.py`: DataSource, Dataset, DatasetVersion, DatasetRecord | `ingestion/connectors.py`, `ingestion/pipeline.py` | `datasets.py` (datasets, quality, lineage) |
| Data quality & lineage | `ai.py::QualityScore` | `engines/data_quality.py`, `engines/lineage.py` | `datasets.py` |
| Evidence | `evidence.py`: Evidence, EvidenceLink | — | `evidence.py` |
| Frameworks / standards | `frameworks.py`: Framework, FrameworkVersion, Requirement, FrameworkMapping, OrganizationFramework | `engines/frameworks.py` | `frameworks.py` |
| Materiality | `materiality.py`: MaterialityAssessment, MaterialityTopic, StakeholderInput | scoring inline in router | `materiality.py` |
| Governance | `governance.py`: GovernancePolicy, GovernanceRule, Issue, Approval | `engines/rules.py`, `services/governance_service.py` | `governance.py` |
| AI | `ai.py`: Agent, AgentRun, ModelRun, KnowledgeDocument, KnowledgeChunk | `ai/*` | `agents.py` (agents, copilot, knowledge) |
| Evaluation | `ai.py::Evaluation` | `ai/agents/evaluation.py`, `engines/readiness.py` | `agents.py::evaluations_router` |
| Reporting | `reporting.py`: ReportTemplate, Report, ReportSection, ReportVersion | `reports/builder.py`, `reports/renderers/*`, `reports/templates/*.yaml` | `reports.py` |
| Audit & notifications | `audit.py`: AuditLog, Notification | `core/audit.py` | `governance.py::audit_router`, `admin.py` |
| Administration | — | `seed/loader.py` | `admin.py` (users, roles, system, reseed, health) |

Contexts communicate through direct Python calls within one process and one database transaction per request; there is no message bus. Cross-context reads (for example the readiness engine reading issues, quality scores, evaluations and report sections) are explicit imports of models, not services.

---

## 3. Request flow

```
Client ── Authorization: Bearer <JWT> ──► main.py middleware
   1. x-request-id bound to structlog context (generated if absent)
   2. per-IP sliding-window rate limit (ESG_RATE_LIMIT_PER_MINUTE, default 600) → 429 envelope
   3. route handler
        deps.User  → core.security.get_principal (decode JWT, load user + role assignments → Principal)
        require(cap) → Principal.has(cap) else 403 {"error":{"code":"forbidden"}}
        deps.DB    → SessionLocal (one session per request, closed in finally)
        get_org / get_period / get_entity / get_metric → tenant + entity scoping, 404 on miss
        … engine / service calls …
        audit.record(...) (flush) → db.commit()
   4. response headers: x-request-id, x-response-time-ms, x-content-type-options, x-frame-options, referrer-policy
   5. structured access log {method, status, latency_ms, request_id, path}
```

Errors are normalised by `core/errors.py::install_error_handlers` into `{"error": {"code", "message", "details"}}` for `AppError` subclasses (`not_found` 404, `forbidden` 403, `unauthorized` 401, `conflict` 409, `governance_blocked` 422, `guardrail_rejected` 422), request validation (`validation_error` 422) and Starlette HTTP exceptions (`http_error`).

Default period resolution (`deps.get_period`): when no `period` is supplied, the latest reporting period **that has at least one metric value** is used (FY2023 in the seed; FY2024 exists but is empty).

---

## 4. Deterministic engines (`app/engines/`)

| Engine | Module | Input → Output | Notes |
|---|---|---|---|
| Safe expression evaluator | `safe_expr.py` | expression string + context → value | AST whitelist (`_ALLOWED_NODES`), no imports/lambdas/comprehensions/dunders, whitelisted `SAFE_FUNCTIONS`; `Ctx` gives attribute access (`metric.code`). Shared by formulas and rule conditions. Placeholders `{CODE}`, `{CODE@prev}`, `{CODE@entity:EEL}` are compiled to variables by `compile_formula`. |
| Metric engine | `metric_engine.py` | (metric, entity, period) → `CalcResult` | Uses the current `CalculationVersion` (fallback `MetricDefinition.formula`, version `"{metric.version}.0"`); resolves inputs via `get_value` (own value, else consolidation of children); persists a `CalculationRun` (inputs, formula, version, status `ok|missing_inputs|error`); writes the result to `MetricValue` **unless** the value is `source_type="reported"` (then only `calculation_run_id` is linked so the quality engine can compare). `recalculate_all` is topologically ordered and raises on circular formulas. |
| Consolidation | `consolidation.py` | (metric, parent entity, period) → `AggregateResult` | Factor: `0` when `in_reporting_boundary=False` or method `equity|excluded`; `ownership_pct/100` for `proportional`; `1` for `full`. Aggregation `sum|avg|weighted_avg|max|last|none`; recursive when a child has no own value; reports `coverage` (share of children with data) and per-child `contributions`. |
| Data quality | `data_quality.py` | (metric, entity, period) → `QualityResult` (7 dimensions, 0–100, explanation list) | Weights: completeness .20, accuracy .20, consistency .15, timeliness .10, validity .15, uniqueness .05, traceability .15. See [EVALUATION.md](EVALUATION.md) for every deduction. |
| Lineage | `lineage.py` | (metric, entity, period) → `{nodes, edges}` and textual chain | Node kinds `metric`, `calculation`, `input`, `dataset`, `source`, `evidence`; recurses into input metrics up to depth 4. Computed on demand — there are no lineage tables. |
| Rules | `rules.py` | rules + context → `RuleOutcome[]`; `upsert_issue`; `resolve_stale` | Context builders per scope; issue fingerprint = sha1(rule, metric, entity, period, requirement)[:40]; `blocks_report` when action ∈ {BLOCK, BLOCK_REPORT_GENERATION, PREVENT_DATA_MODIFICATION} or severity CRITICAL. |
| Readiness | `readiness.py` | (org, period, frameworks, report?) → `Readiness` | Weighted blend of 7 components, open-issue penalties, `ready_to_publish = no blocking issues and overall ≥ 80`. Formula in [GOVERNANCE.md](GOVERNANCE.md#8-report-readiness-enginesreadinesspy). |
| Frameworks | `frameworks.py` | YAML → registry tables; (org, period, framework) → coverage | `requirement_status` yields `complete|partial|missing|omitted`; alignment = (complete + 0.5·partial) / applicable leaf requirements. See [FRAMEWORKS.md](FRAMEWORKS.md). |

Engines never call the AI layer. The AI layer calls engines only through the tool registry.

---

## 5. AI orchestration layer (`app/ai/`)

```
copilot.ask(question)
  └─ guardrails.check_input ─► moe.classify (keyword scoring → ≤2 experts)
        └─ for each expert: agents.registry.get(expert.agent)(db, principal).run(task, payload, expert_hint)
              BaseAgent.run:
                input guardrail → gather() via tools (deterministic facts)
                → provider.complete(system=BASE_SYSTEM, user=prompt + FACTS json, json_schema?)  [anthropic | offline]
                → compose() → output guardrail (numbers vs facts, citations, compliance claims, leakage, framework mismatch)
                → evaluation.score_output (factuality, groundedness, relevance, citations, numerical consistency)
                → governance_service.check_ai_output (rules, scope ai_output)
                → status completed | requires_review | blocked  → persist AgentRun, Evaluation, ModelRun[]
        └─ moe.aggregate(responses) → answer, sources, metrics_used, experts, route, disclaimer
```

Components:

- **Providers** (`ai/llm/`): `LLMProvider` protocol (`complete(system, messages, json_schema, max_tokens, effort, purpose) → LLMResult`), `ProviderRegistry`, `get_provider()` with safe degradation to `OfflineProvider`. `AnthropicProvider` uses `client.messages.stream(...)`, `thinking={"type": "adaptive"}`, `output_config.effort`, `output_config.format` (JSON schema) and `cache_control` on the system block; refusals are surfaced as `LLMResult.refusal`.
- **Controlled tools** (`ai/tools/registry.py`): 14 functions registered with `@tool`, each taking a `ToolContext(db, principal)` that enforces tenant and entity scope. JSON schemas are derived from signatures (`anthropic_tool_definitions`).
- **Agents** (`ai/agents/`): `AgentSpec` + `BaseAgent` pipeline; 10 specialists in `specialists.py`; `registry.py` maps codes to classes.
- **Evaluation** (`ai/agents/evaluation.py`): deterministic scoring, reproducible.
- **Guardrails** (`ai/guardrails/__init__.py`): input (prompt injection, sensitive patterns, size, unsupported upload formats), ESG value validation, output (unsupported numbers, citations, compliance claims, leakage, framework mismatch).
- **MoE** (`ai/moe/__init__.py`): 11 experts, keyword routing, aggregation.
- **RAG** (`ai/rag/`): `LexicalIndex` BM25 per tenant, `PgVectorIndex` adapter, `retrieve()` with permission and kind filters and reranking.

Full detail: [AGENTS.md](AGENTS.md), [RAG.md](RAG.md).

---

## 6. Application services

### Ingestion (`app/ingestion/`)

`IngestionPipeline.ingest()` implements *source → raw → validation → normalisation → quality → load*:

1. Upload guardrail on file extension (`SUPPORTED_UPLOADS`).
2. Resolve `DataSource` and `Dataset` (created on first use); idempotency on `DatasetVersion.idempotency_key`.
3. Connector by kind (`CONNECTORS`: csv, json, excel, pdf, text) → row dicts; SHA-256 of the file; new `DatasetVersion` (status `received`).
4. Tabular rows: alias normalisation (`ALIASES`), metric/entity/period resolution, ESG value guardrail (`validate_esg_value`), per-row `DatasetRecord` with `issues` and `is_valid`; version status `validated|failed`, `validation_result`, `quality` (`data_quality.dataset_quality`).
5. Documents (pdf/text): page text and candidate `label: number` facts stored as records for the ESG Data Agent to map.
6. `load()`: for valid rows, `check_data_change` (governance, scope `data_change`), upsert `MetricValue` (status `draft`, `source_type="ingested"`, linked `dataset_version_id`); a value that is `approved|final` **and** `reported` is not overwritten (record gets a `locked_value` issue). Each change is audited.

### Governance service (`app/services/governance_service.py`)

`run_metric_rules` evaluates `metric_value` rules over every value in a period plus every KPI at group level (to raise "missing" issues), upserts issues, and auto-resolves stale `evidence_gap`/`data_missing` issues. `check_ai_output`, `check_data_change` (raises `GovernanceBlockedError`) and `check_report` (builds the report context and returns blocking reasons) complete the set. Triggers: value upsert, evidence link, status transitions, recalculation, seeding, worker, report validation.

### Report builder (`app/reports/builder.py`)

`create` (sections filtered by selected frameworks) → `generate_draft` (data tables from governed values; narrative via the Reporting Agent; data sections rendered deterministically for `targets`, `framework_index`, `methodology`, `assurance`, `appendix`) → `validate` (nine checks; CRITICAL failures block) → `transition_section` / `transition_report` (role-gated states, `approved`/`published` lock the report) → `generate` (renderer by format, SHA-256, `ReportVersion`; `final=True` re-validates and requires an approved report). Draft files carry the watermark `DRAFT — NOT FOR DISTRIBUTION`.

---

## 7. Extensibility patterns

| Extension | Mechanism | Guide |
|---|---|---|
| Metric | YAML entry in `seed/ecorp_2023/metrics_*.yaml` or `POST /metrics`; formulas in the `{CODE}` DSL | [guides/add-metric.md](guides/add-metric.md) |
| Framework | YAML file in `frameworks/`; loaded idempotently by `engines/frameworks.py::load_from_yaml` (startup seed or `POST /frameworks/reload`) | [guides/add-framework.md](guides/add-framework.md) |
| Agent | Subclass `BaseAgent`, declare `AgentSpec`, implement `gather`, register in `ai/agents/registry.py` | [guides/add-agent.md](guides/add-agent.md) |
| Tool | `@tool("description")` function in `ai/tools/registry.py` with `ToolContext` first parameter | [guides/add-agent.md](guides/add-agent.md) |
| Expert (MoE) | `Expert(...)` entry in `ai/moe/__init__.py::EXPERTS` | [AGENTS.md](AGENTS.md) |
| LLM provider | Class implementing `LLMProvider`, registered via `ai/llm/base.py::registry` and `get_provider` | [AGENTS.md](AGENTS.md) |
| Vector index | Implement `ai/rag/index.py::Index.search`, swap in `retrieve()` | [RAG.md](RAG.md) |
| Connector | `@connector("kind")` in `ingestion/connectors.py` + `detect_kind` mapping | [guides/add-connector.md](guides/add-connector.md) |
| Report section / template | YAML in `reports/templates/`; data sections handled in `ReportBuilder._data_section` | [guides/add-report-section.md](guides/add-report-section.md) |
| Renderer | Module with `render(payload) -> bytes` registered in `reports/builder.py::RENDERERS` | [guides/add-report-section.md](guides/add-report-section.md) |
| Governance rule | YAML in `seed/ecorp_2023/governance.yaml` or `POST /governance/rules` | [guides/add-governance-rule.md](guides/add-governance-rule.md) |
| Rule action | Add to `models/governance.py::RULE_ACTIONS`, `engines/rules.py::BLOCKING_ACTIONS` (if blocking) and `governance_service.CATEGORY_BY_ACTION` | [GOVERNANCE.md](GOVERNANCE.md) |
| Worker job | Callable in `app/worker.py::JOBS` | [DEPLOYMENT.md](DEPLOYMENT.md) |

---

## 8. Life of a metric value

The sequence below follows `SOC.OHS.TRIR_EMP` (employee TRIR) for `ECORP`, `FY2023`.

```
1. Definition      seed metrics_social.yaml → MetricDefinition(code, kind=derived, formula
                   "safe_div(nz({SOC.OHS.RECORDABLE_EMP}) * 200000, {SOC.OHS.HOURS_EMP})",
                   validation {tolerance_pct: 10}) + CalculationVersion v1.0 (is_current)
2. Reported value  seed → MetricValue(value_numeric=0.09, status=final, source_type=reported,
                   confidence=0.95) + EvidenceLink → Evidence EV-RPT23-P67 (printed page 67, PDF page 36)
                   + dataset_version_id → DS-RPT-SOC v1 (source SRC-REPORT-2023)
3. Inputs          SOC.OHS.RECORDABLE_EMP = 3, SOC.OHS.HOURS_EMP = 6,840,000 (both reported, P67)
4. Calculation     metric_engine.calculate → compile_formula → evaluate → 0.087719…
                   CalculationRun(status=ok, inputs={code: {value, metric_value_id, entity, period}})
                   reported value NOT overwritten; MetricValue.calculation_run_id linked
5. Quality         data_quality.assess → consistency: |0.0877 − 0.09| / 0.09 = 2.5 % ≤ tolerance 10 %
                   → note "Reported value agrees with recalculation"; traceability: verified evidence
                   linked → QualityScore(overall …) and MetricValue.quality_score
6. Governance      run_metric_rules → context {metric.is_kpi, evidence_count=1, verified_evidence_count=1,
                   status=final, …} → GR-001…GR-006 evaluated; none triggered → no Issue
7. Lineage         lineage.build → metric → calculation v1.0 → inputs (recursed) → dataset DS-RPT-SOC v1
                   → source SRC-REPORT-2023 → evidence EV-RPT23-P67
8. Framework       requirement_status(WEF.PEOPLE.HEALTH_SAFETY, GRI.403-9, SASB.RT-CH-320a.1, SDG.3):
                   has_value=True, has_evidence=True → contributes to "complete"
9. AI              Copilot "Explain how the contractor TRIR is calculated" → GHG/statistics expert →
                   Calculation Agent → tool calculate_metric (persist=False) → FACTS → provider text
                   → output guardrail (0.09, 0.0877, 200,000, 6,840,000 all in facts) → evaluation → GR-010/011/012
10. Report         ESG_ANNUAL section "ohs" lists SOC.OHS.TRIR_EMP → table row [value 0.09, prior 0.06,
                   evidence EV-RPT23-P67]; Reporting Agent narrative; check 6 (numerical consistency) verifies
                   every number in the narrative against governed values
11. Approval       section requires_review → reviewed (reviewer) → approved (report_approver);
                   report approved → locked; GR-020 prevents further data modification for FY2023
12. Audit          every step above wrote audit_logs rows (data.modify, calculation.run, evidence.link,
                   ai.copilot, report.validate, report_section.approved, report.approved, …)
```

---

## 9. Runtime topology

| Process | Entry point | Role |
|---|---|---|
| API | `uvicorn app.main:app` (Dockerfile: `alembic upgrade head && uvicorn … --workers ${WEB_CONCURRENCY:-2}`) | Serves `/api/v1`, `/health`, `/health/ready`; runs `create_all` (dev/test) and `seed_if_needed` in the lifespan |
| Worker | `python -m app.worker` | Consumes `esg:jobs` from Redis (`{"job": "recompute", "kwargs": {...}}`) or runs `job_recompute` every 6 h |
| Frontend | nginx (Docker) / Vite dev server | Static SPA, proxies `/api` |

State lives in the database and `ESG_LOCAL_STORAGE_DIR` (report files, uploaded evidence). API processes are otherwise stateless apart from the in-memory rate-limit buckets and the per-tenant BM25 index cache (`_INDEX_CACHE`, rebuilt when the chunk count changes).
