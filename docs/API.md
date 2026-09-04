# API Reference

Versioned REST API served by `backend/app/main.py`. All application routes are mounted under `ESG_API_PREFIX` (default `/api/v1`); the health routes are mounted at the root. Interactive documentation: `/api/v1/docs` (Swagger UI), `/api/v1/redoc`, schema `/api/v1/openapi.json`.

Related: [SECURITY.md](SECURITY.md) (roles and capabilities) · [ARCHITECTURE.md](ARCHITECTURE.md#3-request-flow).

---

## 1. Conventions

### Authentication

Bearer JWT (HS256, signed with `ESG_SECRET_KEY`). Obtain tokens from `POST /auth/login`; access tokens expire after `ESG_ACCESS_TOKEN_MINUTES` (default 480), refresh tokens after `ESG_REFRESH_TOKEN_DAYS` (default 14). Every route except `/auth/login`, `/auth/refresh`, `/health`, `/health/ready` and `/` requires `Authorization: Bearer <access_token>`.

### Capabilities

The **Capability** column names the capability enforced by `require(<capability>)` (`app/core/security.py::CAPABILITIES`). `read` means any authenticated user. Some endpoints enforce capability inside the handler (noted as *handler-checked*). Role → capability matrix: [SECURITY.md](SECURITY.md#2-rbac-matrix).

### Common query parameters

| Parameter | Meaning |
|---|---|
| `period` | Reporting period code (`FY2023`). Default: latest period that has metric values. |
| `entity` | Entity code (`EFERT`). Default: the `group` entity. |
| `org_id` | Organisation id. Default: the principal's first organisation. |

### Pagination

List endpoints marked *paginated* accept `limit` (1–500, default 50), `offset` (default 0), `sort` (column name of the model) and `order` (`asc`|`desc`) and return

```json
{"items": [...], "total": 123, "limit": 50, "offset": 0}
```

### Error envelope

All errors share one shape (`app/core/errors.py`):

```json
{"error": {"code": "forbidden", "message": "Capability 'metric.write' required", "details": {"roles": ["auditor"]}}}
```

| HTTP | `code` | Raised by |
|---|---|---|
| 400 | `app_error` | Generic `AppError` (invalid rule condition, unknown role, exception without reason) |
| 401 | `unauthorized` | Missing/invalid/expired token, inactive user, bad credentials |
| 403 | `forbidden` | Missing capability, entity scope, workflow transition not permitted |
| 404 | `not_found` | Unknown organisation, period, entity, metric, evidence, report, … |
| 409 | `conflict` | Reserved (`ConflictError`) |
| 422 | `validation_error` | Pydantic request validation (`details` = list of field errors) |
| 422 | `governance_blocked` | A governance rule with a blocking action (`details`: rule, reason, required_action) |
| 422 | `guardrail_rejected` | Input guardrail rejected a value or file (`details`: findings) |
| 429 | `rate_limited` | Per-IP limit (`ESG_RATE_LIMIT_PER_MINUTE`) exceeded |
| 4xx/5xx | `http_error` | Starlette HTTP exceptions |

### Response headers

`x-request-id` (echoed or generated), `x-response-time-ms`, `x-content-type-options: nosniff`, `x-frame-options: DENY`, `referrer-policy: strict-origin-when-cross-origin`.

### Serialisation

Model responses are column dictionaries (`deps.serialize`); dates and datetimes are ISO-8601 strings. Passwords hashes are never returned.

---

## 2. Endpoints

### 2.1 Health (no prefix)

| Method | Path | Capability | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness: `{"status":"ok","app","uptime_seconds"}` |
| GET | `/health/ready` | none | Readiness: executes `SELECT 1`, counts tenants → `{"status":"ready","database":"ok","tenants":1,"seeded":true}` or `{"status":"degraded","error"}` |
| GET | `/` | none | `{"app","docs","health"}` (excluded from schema) |

### 2.2 Auth — `/auth`

| Method | Path | Capability | Purpose |
|---|---|---|---|
| POST | `/auth/login` | none | Body `{"email","password"}` → `{"access_token","refresh_token","token_type":"bearer","user":{id,email,full_name,tenant_id,roles,capabilities,title}}`. Audited as `auth.login`. |
| POST | `/auth/refresh` | none | Body `{"refresh_token"}` → new `access_token` + `user` |
| GET | `/auth/me` | read | Current principal with roles and computed capabilities |

```bash
curl -s -X POST localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"manager@ecorp.local","password":"Manager!2024"}'
```

### 2.3 Organizations — `/organizations`

| Method | Path | Capability | Purpose / key params |
|---|---|---|---|
| GET | `/organizations` | read | Organisations visible to the principal |
| GET | `/organizations/{org_id}` | read | Organisation + `periods` + `entities` (nested tree from `consolidation.tree`) |
| GET | `/organizations/{org_id}/entities` | read | `flat=true` for a flat list, else nested tree with consolidation settings |
| POST | `/organizations/{org_id}/entities` | admin | Body `EntityIn` (`code, name, kind, parent_code, ownership_pct, consolidation_method, in_reporting_boundary, country, region, location, sector, description, attributes`) |
| GET | `/organizations/{org_id}/periods` | read | Reporting periods ordered by start date |
| POST | `/organizations/{org_id}/periods` | admin | Body `PeriodIn` (`code, label, start_date, end_date, granularity, status`) |

### 2.4 ESG intelligence — `/esg`

| Method | Path | Capability | Purpose / key params |
|---|---|---|---|
| GET | `/esg/overview` | read | Executive dashboard: `readiness`, 16 `kpis` (`OVERVIEW_KPIS` cards), `issues` summary and top 8, `coverage`, `what_changed` (cards with |YoY| ≥ 5 %). Params `period, entity, org_id`. |
| GET | `/esg/topics` | read | Taxonomy with subtopics |
| GET | `/esg/pillar/{pillar}` | read | Topics of a pillar with KPI cards and narrative values; `kpi_only=true` |
| GET | `/esg/entity-comparison` | read | `metric=<code>`: value and prior value per entity |

KPI card shape (`esg.kpi_card`): `code, name, unit, pillar, topic, kind, direction, value, previous, yoy_pct, trend (improving|worsening|up|down|flat), period, previous_period, target {value,year,direction,status}, target_status (on_track|above_target|below_target|off_target|target_not_set|no_target), data_unavailable, source_type, is_estimate, evidence_count, quality_score, open_issues, assurance_status, is_kpi`.

### 2.5 Metrics — `/metrics`

| Method | Path | Capability | Purpose / key params |
|---|---|---|---|
| GET | `/metrics` | read | *paginated*; filters `pillar, topic, kpi, q, kind, framework` |
| POST | `/metrics` | metric.write | Body `MetricIn`; a `formula` also creates `CalculationVersion 1.0` |
| GET | `/metrics/kpis` | read | KPI cards for `period, entity, pillar` |
| GET | `/metrics/{code}` | read | Definition + `calculation_versions` + `framework_requirements` |
| GET | `/metrics/{code}/detail` | read | Interactive detail: `card, series, value, calculation, evidence, quality, governance, issues, targets, lineage, audit_history, ai_analysis` |
| GET | `/metrics/{code}/values` | read | All values (optionally `period`) with entity/period codes |
| POST | `/metrics/{code}/values` | data.write | Body `ValueIn` (`entity_code, period_code, value_numeric, value_text, is_estimate, confidence, notes, reason, evidence_codes`). Runs data-change governance, input guardrail (HIGH finding → 422 `guardrail_rejected`), upsert (status `draft`, `manual`), evidence links, audit, `recalculate_all`, quality assessment and rule run. |
| POST | `/metrics/{code}/status` | handler-checked: `validated`→metric.validate, `approved`/`final`→metric.approve, `draft`→data.write | Body `StatusIn` (`entity_code, period_code, status, comment`) |
| POST | `/metrics/{code}/calculate` | metric.write | Params `entity, period, persist` (default true) → `CalcResult` + `explanation` |
| POST | `/metrics/{code}/formula` | metric.approve | Body `FormulaIn` (`formula, version, description`): syntax-checks, retires current version, creates new current version, bumps `metric.version` |
| GET | `/metrics/{code}/lineage` | read | `{graph:{nodes,edges}, chain:[...]}` |
| GET | `/metrics/{code}/runs` | read | Latest calculation runs (`limit`, default 20) |

Example — recalculate employee TRIR without persisting:

```bash
curl -s -X POST "localhost:8000/api/v1/metrics/SOC.OHS.TRIR_EMP/calculate?period=FY2023&persist=false" -H "authorization: Bearer $T"
```
```json
{"metric_code":"SOC.OHS.TRIR_EMP","entity_code":"ECORP","period_code":"FY2023","value":0.08771929824561403,"status":"ok",
 "formula":"safe_div(nz({SOC.OHS.RECORDABLE_EMP}) * 200000, {SOC.OHS.HOURS_EMP})","version":"1.0",
 "inputs":{"SOC.OHS.RECORDABLE_EMP":{"value":3.0,"metric_value_id":…,"entity":"ECORP","period":"FY2023"},
           "SOC.OHS.HOURS_EMP":{"value":6840000.0,"metric_value_id":…,"entity":"ECORP","period":"FY2023"}},
 "message":null,"run_id":null,"explanation":"Formula (version 1.0): …\n  SOC.OHS.RECORDABLE_EMP = 3.0 [ECORP, FY2023]\n  …\nResult: 0.0877…"}
```

### 2.6 Targets — `/targets`

| Method | Path | Capability | Purpose |
|---|---|---|---|
| GET | `/targets` | read | Targets with `current_value`, `current_period`, `progress_pct` ((current − baseline)/(target − baseline)); filter `status` |
| POST | `/targets` | metric.write | Body `TargetIn` (`metric_code, entity_code, target_value, baseline_value, target_year, direction, kind, description, status`) |

### 2.7 Calculations — `/calculations`

| Method | Path | Capability | Purpose |
|---|---|---|---|
| POST | `/calculations/recalculate` | metric.write | Params `period, org_id`: dependency-ordered recalculation of every derived metric for every entity, then quality assessment and rule run → `{period, calculated, missing_inputs, errors[], governance{…}}` |
| GET | `/calculations/versions` | read | All formula versions with metric code/name |

### 2.8 Data — `/datasets`, `/quality`, `/lineage`

| Method | Path | Capability | Purpose / key params |
|---|---|---|---|
| GET | `/datasets/sources` | read | Data sources with `dataset_count` |
| POST | `/datasets/sources` | admin | Body `SourceIn` (`code, name, kind, system_name, owner, description, config`) |
| GET | `/datasets` | read | *paginated*; filters `source, pillar`; items carry `source_*`, `latest_version`, `version_count` |
| GET | `/datasets/{dataset_id}` | read | Dataset + source + versions |
| GET | `/datasets/versions/{version_id}/records` | read | *paginated*; `only_invalid=true` |
| POST | `/datasets/upload` | data.write | `multipart/form-data`: `file` (csv, xlsx/xls/xlsm, json, pdf, txt/md), `source_code` (default `SRC-MANUAL`), `dataset_code`, `dataset_name`, `entity_default`, `period_default`, `auto_load` (default true), `idempotency_key` → `{status, dataset_version_id, version, rows, valid_rows, loaded_values, quality, validation_result}`; `status: "duplicate"` when the idempotency key was seen; `"rejected"` with `guardrail` for unsupported files |
| POST | `/datasets/versions/{version_id}/load` | data.write | Load valid records into metric values |
| POST | `/datasets/classify` | ai.run | Body `{"columns":[...], "rows":[{...}]}` → ESG Data Agent result (`mappings`, `findings`, `summary`) |
| GET | `/quality/summary` | read | Period averages per dimension, `by_pillar`, 15 `lowest` values with explanations |
| GET | `/quality/scores` | read | *paginated*; filters `period, metric, entity, max_score` |
| POST | `/quality/assess` | metric.validate | `metric`+`entity` for one value, otherwise every value in `period` |
| GET | `/lineage` | read | `metric` (required), `entity`, `period` → `{graph, chain}` |

CSV expected columns (aliases accepted): `metric_code` (`metric`, `code`), `entity_code` (`entity`, `company`), `period_code` (`period`, `year`, `fy`; numeric years become `FY<year>`), `value` (`amount`, `val`), optional `unit`.

### 2.9 Evidence — `/evidence`

| Method | Path | Capability | Purpose / key params |
|---|---|---|---|
| GET | `/evidence/kinds` | read | `EVIDENCE_KINDS` |
| GET | `/evidence` | read | *paginated*; filters `kind, status, q, metric`; items carry `link_count`, truncated `excerpt` |
| GET | `/evidence/gaps` | read | `{period, required, covered, coverage_pct, gaps[], unverified_evidence, open_issues[]}` |
| GET | `/evidence/{code}` | read | Evidence with `links` (metric, entity, period, value, relation) |
| POST | `/evidence` | evidence.write | Body `EvidenceIn` (`code, title, kind, source, document_ref, page_from, page_to, printed_page, excerpt, evidence_date, entity_code, period_code, confidence, metric_codes[]`) |
| POST | `/evidence/upload` | evidence.write | `multipart/form-data`: `file, code, title, kind, metric_code, entity_code, period_code`; file stored under `ESG_LOCAL_STORAGE_DIR/evidence`, SHA-256 recorded |
| POST | `/evidence/{code}/link` | evidence.write | Body `LinkIn` (`metric_code, entity_code, period_code, relation, note`); re-assesses quality and rules for the linked value |
| POST | `/evidence/{code}/verify` | evidence.verify | Body `VerifyIn` (`status: verified|rejected|unverified, comment, confidence`) |

### 2.10 Standards — `/frameworks`

| Method | Path | Capability | Purpose / key params |
|---|---|---|---|
| GET | `/frameworks` | read | Registry with `current_version`, `effective_date`, `requirement_count`, `versions` |
| GET | `/frameworks/selected` | read | Frameworks selected for `period` (`organization_frameworks`) |
| POST | `/frameworks/select` | framework.manage | Body `SelectIn` (`framework_codes[], period_code, applicable_scope`) |
| POST | `/frameworks/reload` | framework.manage | Re-load every `frameworks/*.yaml` → `{loaded:[codes]}` |
| GET | `/frameworks/{code}/requirements` | read | Requirements of the current version |
| GET | `/frameworks/{code}/coverage` | read | Coverage for `period`: `alignment_pct, applicable, completed, partial, missing, omitted, evidence_gaps, metric_gaps, narrative_gaps, requirements[], disclaimer` |
| GET | `/frameworks/requirements/{req_code}` | read | Requirement status + tenant `mappings` |
| POST | `/frameworks/mappings` | framework.manage | Body `MappingIn` (`requirement_code, metric_code, mapping_type, rationale, omission_reason, confidence`) — `mapping_type: "omitted"` records an approved omission |
| GET | `/frameworks/mappings/all` | read | All tenant mappings |
| POST | `/frameworks/gap-analysis` | ai.run | Params `framework` (default `WEF_SCM`), `period` → Standards Mapping Agent result |

### 2.11 Materiality — `/materiality`

| Method | Path | Capability | Purpose / key params |
|---|---|---|---|
| GET | `/materiality/assessments` | read | Assessments with topic counts |
| GET | `/materiality/assessments/{id}` | read | Topics with `related_metrics` (group values), matrix coordinates `x` (financial), `y` (impact), `size` (stakeholder priority), `stakeholder_inputs`, axis labels and threshold |
| PUT | `/materiality/assessments/{id}/topics/{topic_code}` | metric.write | Body `TopicScoreIn`; recomputes `impact_score`, `financial_score`; `is_material` derived from `max(scores) ≥ threshold` unless supplied |
| POST | `/materiality/assessments/{id}/stakeholders` | metric.write | Body `StakeholderIn` |
| POST | `/materiality/analyze` | ai.run | Materiality Agent (`assess` task) |

### 2.12 Governance — `/governance`, `/audit`

| Method | Path | Capability | Purpose / key params |
|---|---|---|---|
| GET | `/governance/policies` | read | Policies |
| POST | `/governance/policies` | governance.manage | Body `PolicyIn` |
| GET | `/governance/rules` | read | `{rules[], actions[], severities[], scopes[]}`; filter `scope` |
| POST | `/governance/rules` | governance.manage | Body `RuleIn` (`code, description, severity, scope, condition, action, message, required_action, owner, version, effective_date, approval_status, policy_code`); the condition is syntax-checked with `safe_expr`; `is_active = approval_status == "approved"` |
| PUT | `/governance/rules/{code}` | governance.manage | Body `RuleUpdate` (partial) |
| POST | `/governance/rules/test` | read | Body `{"condition","context"}` → `{"result": bool}` or `{"error"}` |
| POST | `/governance/rules/run` | metric.validate | Params `period, org_id` → `{rules_evaluated, evaluations, issues_triggered, auto_resolved, triggered[]}` |
| GET | `/governance/issues` | read | *paginated*, ordered by severity; filters `severity, status (open (default; includes acknowledged) | all | <status>), category, metric, period`; plus `open_by_severity` |
| POST | `/governance/issues/{code}/acknowledge` | metric.validate | Body `{"comment"}` |
| POST | `/governance/issues/{code}/resolve` | metric.approve | Body `{"comment"}` |
| POST | `/governance/issues/{code}/exception` | governance.exception | Body `{"comment"}` (required) → status `exception_approved`, `blocks_report=false`, an `approvals` row |
| GET | `/governance/approvals` | read | `pending=true` (default) → undecided only |
| POST | `/governance/approvals` | review | Body `ApprovalIn` (`object_type, object_id, assigned_to, context`) |
| POST | `/governance/approvals/{id}/decide` | review (+ workflow `approved` for report/exception objects) | Body `DecisionIn` (`decision: approved|rejected|changes_requested, comment`) |
| GET | `/audit` | audit.read | *paginated*; filters `action` (prefix), `object_type, object_id, user_id, q, date_from, date_to`; items carry `user_email` |

### 2.13 AI — `/agents`, `/copilot`, `/knowledge`, `/evaluations`

| Method | Path | Capability | Purpose / key params |
|---|---|---|---|
| GET | `/agents` | read | Agent specs with run counts and average confidence; `provider`, `model` |
| GET | `/agents/tools` | read | Controlled tool registry with JSON schemas |
| GET | `/agents/runs` | read | *paginated*; filters `agent, status` |
| GET | `/agents/runs/{run_id}` | read | Run + `evaluation` + `model_runs` |
| POST | `/agents/{code}/run` | ai.run | Body `{"task","payload"}` → `AgentResult` (`agent, task, status, output, confidence, sources, metrics_used, tools_used, guardrail, evaluation, governance, run_id, provider, latency_ms, requires_human_review, blocked`) |
| POST | `/copilot/ask` | ai.run | Body `AskIn` (`question, period_code, entity_code, frameworks[]`) → answer, `confidence`, `sources`, `metrics_used`, `evidence`, `route`, `experts`, `relevant_frameworks`, `agent_runs`, `guardrail`, `status`, `disclaimer`, `extras` |
| GET | `/copilot/experts` | read | MoE expert table |
| GET | `/copilot/suggestions` | read | Ten suggested questions |
| GET | `/knowledge/documents` | read | Documents with chunk counts and `accessible` flag for the principal |
| POST | `/knowledge/search` | read | Body `{"query","limit","kind"}` → permission-filtered hits with citations (`index: "lexical-bm25"`) |
| GET | `/evaluations` | read | *paginated*; filters `dimension, object_type` |
| GET | `/evaluations/summary` | read | Evaluation centre: `data_quality`, `ai_quality`, `esg_quality`, `report_quality`, `readiness`, `overall_scores`, `observability` |
| GET | `/evaluations/readiness` | read | Readiness for `period`, `frameworks` (comma list, default `WEF_SCM,UNGC,UN_SDG`) |
| GET | `/evaluations/trend` | read | Last 100 AI evaluations over time |

Example — Copilot:

```bash
curl -s -X POST localhost:8000/api/v1/copilot/ask -H "authorization: Bearer $T" -H 'content-type: application/json' \
  -d '{"question":"Why did our Scope 1 emissions increase in FY2023?"}'
```
```json
{"answer":"Scope 1 GHG emissions was 7,327,238 tCO2e for ECORP in FY2023, an increase of 6.6% against the prior period (6,871,414 tCO2e) [ENV.GHG.SCOPE1 · ECORP · FY2023]. … Sources: …",
 "confidence":0.9,"sources":["[ENV.GHG.SCOPE1 · ECORP · FY2023]","[EV-RPT23-P81]","[KB-REPORT-2023 p.81-82]"],
 "metrics_used":["ENV.GHG.SCOPE1", "…"],"route":{"primary":"ghg","experts":["ghg","statistics"],"scores":{…},"method":"keyword"},
 "status":"completed","disclaimer":"Answers are generated from governed metrics and approved knowledge with citations; they are advisory and do not constitute a compliance opinion."}
```

### 2.14 Reports — `/reports`

| Method | Path | Capability | Purpose / key params |
|---|---|---|---|
| GET | `/reports/templates` | read | Templates from `reports/templates/*.yaml` |
| GET | `/reports` | read | *paginated*; filter `status`; items carry `period_code, organization_name, section_count, approved_sections, versions` |
| POST | `/reports` | report.build | Body `ReportIn` (`period_code, template_code=ESG_ANNUAL, title, framework_codes=[WEF_SCM,UNGC,UN_SDG], scope, org_id`) → report detail |
| GET | `/reports/{id}` | read | Report + `sections` + `versions` |
| POST | `/reports/{id}/generate-draft` | report.build | Param `sections` (comma list) → builds tables, AI narratives, data sections; status `ai_generated` |
| POST | `/reports/{id}/validate` | report.build | Nine checks → `{blocked, checks[], readiness, governance[], reason[], required_action[]}` |
| GET | `/reports/{id}/preview` | read | Paginated preview `{pages[{number,title,html,code,status}], css, title, status, readiness}` |
| GET | `/reports/{id}/preview.html` | read | Full HTML document |
| PUT | `/reports/{id}/sections/{code}` | handler-checked (edit needs report.build or review; state needs workflow permission) | Body `SectionIn` (`state, content_md, comment`) |
| POST | `/reports/{id}/sections/{code}/regenerate` | report.build | Re-draft one section |
| POST | `/reports/{id}/transition` | workflow transition (`WORKFLOW_TRANSITIONS`) | Body `{"state","comment"}`; `approved`/`published` run validation, require all sections approved, lock the report |
| POST | `/reports/{id}/generate` | report.build (+ report.approve when `final=true`) | Params `format` (pdf, docx, xlsx, csv, html), `final` → `ReportVersion` |
| GET | `/reports/{id}/versions` | read | Generated versions |
| GET | `/reports/versions/{version_id}/download` | read | File download with proper media type |

### 2.15 Administration — `/admin`

| Method | Path | Capability | Purpose |
|---|---|---|---|
| GET | `/admin/users` | admin | Users with roles and entity scope |
| POST | `/admin/users` | admin | Body `UserIn` (`email, full_name, password, roles[], entity_code, title`) |
| PUT | `/admin/users/{id}/roles` | admin | Replace role assignments |
| GET | `/admin/roles` | read | Roles with computed capabilities |
| GET | `/admin/system` | admin | Environment, database backend, AI provider/model, tenant, uptime, counts, config |
| POST | `/admin/reseed` | tenant.admin | Re-run the seeder (`recompute` param) |
| GET | `/admin/notifications` | read | Notifications for the user or broadcast; `unread=true` |

---

## 3. Workflow states

Metric values: `draft → validated → approved → final` (`POST /metrics/{code}/status`).

Report sections and reports (`security.WORKFLOW_TRANSITIONS`): `draft, ai_generated, validating, requires_review, reviewed, approved, published, rejected` (+ `blocked` set by validation). Who may enter each state:

| State | Roles |
|---|---|
| draft | super_admin, org_admin, esg_manager, esg_analyst, data_contributor |
| ai_generated, validating, requires_review | super_admin, org_admin, esg_manager, esg_analyst |
| reviewed | super_admin, org_admin, esg_manager, reviewer |
| approved, published | super_admin, org_admin, report_approver |
| rejected | super_admin, org_admin, esg_manager, reviewer, report_approver |

---

## 4. Idempotency

`POST /datasets/upload` honours `idempotency_key` per dataset (returns `status: "duplicate"` with the existing version). Report generation is versioned rather than idempotent: each `POST /reports/{id}/generate` creates a new `report_versions` row with its own SHA-256.
