# Database

ESG Nexus persists 45 tables defined with SQLAlchemy 2.0 declarative models in `backend/app/models/`. The models are dialect-agnostic: SQLite is used for local development and tests (`ESG_DATABASE_URL` default `sqlite:///backend/esg_nexus.db`, WAL mode, foreign keys enforced), PostgreSQL 16 with pgvector in Docker and production.

Related: [ARCHITECTURE.md](ARCHITECTURE.md) · [DATA_MODEL_ESG.md](DATA_MODEL_ESG.md) · [DEPLOYMENT.md](DEPLOYMENT.md#migrations).

---

## 1. Conventions

| Item | Implementation (`app/core/db.py`) |
|---|---|
| Primary keys | `PKMixin`: `id INTEGER PRIMARY KEY AUTOINCREMENT` |
| Timestamps | `TimestampMixin`: `created_at`, `updated_at` (timezone-aware, `utcnow`) |
| Tenant scoping | `TenantMixin`: `tenant_id INTEGER NOT NULL`, indexed (no FK — tenants are resolved by the principal) |
| Naming | `MetaData(naming_convention=NAMING)`: `ix_<column>`, `uq_<table>_<col>`, `ck_<table>_<name>`, `fk_<table>_<col>_<ref>`, `pk_<table>` |
| JSON | `JSON` columns for lists/dicts (payloads, scores, permissions, inputs); portable across SQLite and PostgreSQL |
| Sessions | `SessionLocal` (autoflush off, `expire_on_commit=False`), one session per request via `get_db` |

Global (non-tenant) tables: `tenants`, `roles`, `frameworks` (nullable `tenant_id` for custom frameworks), `framework_versions`, `requirements`, `agents`, `report_templates` (nullable `tenant_id`). Child tables that inherit scope through a parent FK do not carry `tenant_id` (`esg_subtopics`, `dataset_records`, `evidence_links`, `materiality_topics`, `stakeholder_inputs`, `knowledge_chunks`, `report_sections`, `user_roles`).

---

## 2. Entity-relationship diagram

```mermaid
erDiagram
    TENANTS ||--o{ USERS : has
    USERS ||--o{ USER_ROLES : assigned
    ORGANIZATIONS ||--o{ ENTITIES : owns
    ORGANIZATIONS ||--o{ REPORTING_PERIODS : defines
    ENTITIES ||--o{ ENTITIES : parent
    ESG_TOPICS ||--o{ ESG_SUBTOPICS : contains
    METRIC_DEFINITIONS ||--o{ METRIC_VALUES : values
    ENTITIES ||--o{ METRIC_VALUES : for
    REPORTING_PERIODS ||--o{ METRIC_VALUES : in
    METRIC_DEFINITIONS ||--o{ CALCULATION_VERSIONS : formulas
    METRIC_DEFINITIONS ||--o{ CALCULATION_RUNS : executions
    CALCULATION_RUNS o|--o{ METRIC_VALUES : produced
    METRIC_DEFINITIONS ||--o{ TARGETS : targets
    DATA_SOURCES ||--o{ DATASETS : provides
    DATASETS ||--o{ DATASET_VERSIONS : versions
    DATASET_VERSIONS ||--o{ DATASET_RECORDS : rows
    DATASET_VERSIONS o|--o{ METRIC_VALUES : loaded
    EVIDENCE ||--o{ EVIDENCE_LINKS : links
    METRIC_DEFINITIONS o|--o{ EVIDENCE_LINKS : metric
    METRIC_VALUES o|--o{ EVIDENCE_LINKS : value
    REQUIREMENTS o|--o{ EVIDENCE_LINKS : requirement
    FRAMEWORKS ||--o{ FRAMEWORK_VERSIONS : versions
    FRAMEWORK_VERSIONS ||--o{ REQUIREMENTS : requirements
    REQUIREMENTS ||--o{ FRAMEWORK_MAPPINGS : mapped
    METRIC_DEFINITIONS o|--o{ FRAMEWORK_MAPPINGS : to
    ORGANIZATIONS ||--o{ ORGANIZATION_FRAMEWORKS : selects
    FRAMEWORK_VERSIONS ||--o{ ORGANIZATION_FRAMEWORKS : selected
    MATERIALITY_ASSESSMENTS ||--o{ MATERIALITY_TOPICS : scores
    MATERIALITY_ASSESSMENTS ||--o{ STAKEHOLDER_INPUTS : inputs
    GOVERNANCE_RULES ||--o{ ISSUES : raises
    AGENT_RUNS ||--o{ MODEL_RUNS : calls
    EVALUATIONS o|--o{ AGENT_RUNS : scored
    KNOWLEDGE_DOCUMENTS ||--o{ KNOWLEDGE_CHUNKS : chunks
    METRIC_DEFINITIONS ||--o{ QUALITY_SCORES : quality
    REPORTS ||--o{ REPORT_SECTIONS : sections
    REPORTS ||--o{ REPORT_VERSIONS : files
    AGENT_RUNS o|--o{ REPORT_SECTIONS : drafted
    EVALUATIONS o|--o{ REPORT_SECTIONS : evaluated
    USERS ||--o{ AUDIT_LOGS : actor
    USERS ||--o{ NOTIFICATIONS : recipient
```

---

## 3. Tables by context

### 3.1 Identity (`models/identity.py`)

| Table | Purpose | Key columns | Constraints |
|---|---|---|---|
| `tenants` | Tenant registry | `slug` (unique), `name`, `deployment_model` (saas, private_cloud, on_prem, air_gapped), `is_active` | `uq slug` |
| `users` | Accounts | `tenant_id` FK, `email`, `full_name`, `password_hash` (PBKDF2-SHA256), `is_active`, `title` | `uq_users_tenant_email`, ix email |
| `roles` | Role catalogue (9 roles seeded from `security.ROLES`) | `name` (unique), `description` | |
| `user_roles` | Role assignment, optionally scoped | `user_id` FK (cascade), `role_name`, `organization_id` FK?, `entity_id` FK? | A row with `entity_id` restricts the principal to that entity (`Principal.entity_ids`) |

### 3.2 Organization (`models/organization.py`)

| Table | Purpose | Key columns | Constraints |
|---|---|---|---|
| `organizations` | Reporting organisation | `tenant_id`, `code`, `name`, `legal_name`, `legal_form`, `headquarters`, `country`, `stock_ticker`, `sector`, `description`, `reporting_boundary`, `website`, `contact` JSON | `uq_organizations_tenant_code` |
| `entities` | Hierarchy node (group → subsidiary/JV/associate → business_unit/plant/office/foundation/trading) | `organization_id` FK (cascade), `parent_id` self-FK, `code`, `name`, `kind`, `ownership_pct`, `consolidation_method` (full, proportional, equity, excluded), `in_reporting_boundary`, `country`, `region`, `location`, `sector`, `attributes` JSON, `is_active` | `uq_entities_tenant_code`, ix organization_id, ix parent_id |
| `reporting_periods` | FY / quarter / month | `organization_id` FK, `code` (FY2023), `label`, `granularity`, `start_date`, `end_date`, `status` (open, closed, published), `is_baseline` | `uq_periods_org_code` |

### 3.3 ESG taxonomy, metrics, calculations (`models/esg.py`)

| Table | Purpose | Key columns | Constraints |
|---|---|---|---|
| `esg_topics` | Taxonomy (30 topics seeded) | `code`, `name`, `pillar` (environment, social, governance, prosperity), `sort_order` | `uq_topics_tenant_code` |
| `esg_subtopics` | Subtopics | `topic_id` FK (cascade), `code`, `name` | `uq_subtopics_topic_code` |
| `metric_definitions` | Metric metadata (see [DATA_MODEL_ESG.md](DATA_MODEL_ESG.md#2-metric-definition-fields)) | `code`, `name`, `pillar`, `topic_code`, `subtopic_code`, `unit`, `frequency`, `data_type`, `kind`, `formula`, `required_inputs`, `data_sources`, `evidence_required`, `applicable_frameworks` JSON, `materiality_topic`, `assurance_status`, `validation_rules` JSON, `aggregation`, `direction`, `is_kpi`, `is_active`, `version`, `owner` | `uq_metric_definitions_tenant_code`, ix code, ix topic_code |
| `metric_values` | One value per (metric, entity, period) | `value_numeric`, `value_text`, `unit`, `status` (draft, validated, approved, final), `source_type` (manual, ingested, calculated, extracted, reported), `dataset_version_id` FK?, `calculation_run_id` FK?, `quality_score`, `confidence`, `is_estimate`, `notes`, `created_by`, `approved_by` | `uq_metric_values_metric_entity_period`; ix metric_id, entity_id, period_id |
| `targets` | Targets incl. explicit "not set" gaps | `metric_id`, `entity_id`, `baseline_period_id`, `target_period_id`, `target_year`, `baseline_value`, `target_value`, `direction`, `kind`, `status` (active, achieved, missed, not_set), `source_evidence_code` | |
| `calculation_versions` | Versioned, approved formulas | `metric_id`, `version` ("1.0"), `formula`, `description`, `methodology_ref`, `is_current`, `approved_by` | `uq_calc_versions_metric_version` |
| `calculation_runs` | Deterministic execution record (lineage anchor) | `metric_id`, `entity_id`, `period_id`, `calculation_version`, `formula`, `inputs` JSON `{code: {value, metric_value_id, entity, period}}`, `result`, `status` (ok, missing_inputs, error), `message`, `executed_at`, `executed_by` | |

### 3.4 Data ingestion (`models/data.py`)

| Table | Purpose | Key columns | Constraints |
|---|---|---|---|
| `data_sources` | Source systems and connectors | `organization_id` FK, `code`, `name`, `kind` (csv, excel, json, api, database, erp, hr, ems, environmental, document, pdf, scanned, manual), `system_name`, `owner`, `config` JSON, `is_active` | `uq_data_sources_tenant_code` |
| `datasets` | Logical dataset | `source_id` FK (cascade), `code`, `name`, `period_id`?, `entity_id`?, `pillar`, `status`, `permissions` JSON | ix source_id, ix code |
| `dataset_versions` | Immutable upload version | `dataset_id`, `version`, `file_name`, `file_hash` (SHA-256), `storage_key`, `row_count`, `uploaded_by`, `uploaded_at`, `status` (received, validated, normalized, loaded, failed), `validation_result` JSON, `transformation_history` JSON, `quality` JSON, `idempotency_key` | `uq_dataset_versions_dataset_version`, ix idempotency_key |
| `dataset_records` | Row-level raw + normalised data | `version_id` FK (cascade), `row_index`, `payload` JSON, `metric_code`, `entity_code`, `period_code`, `value`, `value_text`, `unit`, `is_valid`, `issues` JSON, `mapping_confidence` | ix version_id, ix metric_code |

### 3.5 Evidence (`models/evidence.py`)

| Table | Purpose | Key columns | Constraints |
|---|---|---|---|
| `evidence` | Evidence item (19 kinds in `EVIDENCE_KINDS`) | `code` (e.g. `EV-RPT23-P80`), `title`, `kind`, `source`, `document_ref`, `page_from`, `page_to`, `printed_page`, `excerpt`, `evidence_date`, `owner_id`, `entity_id`?, `period_id`?, `verification_status` (unverified, verified, rejected), `verified_by`, `confidence`, `version`, `file_hash`, `storage_key`, `permissions` JSON, `meta` JSON | `uq_evidence_tenant_code` |
| `evidence_links` | Evidence → metric / value / requirement / section | `evidence_id` FK (cascade), `metric_id`?, `metric_value_id`?, `requirement_id`?, `report_section_id`?, `relation` (supports, contradicts, context), `note` | ix on each FK |

A link with `metric_id` set and `metric_value_id` NULL applies to every value of the metric; engines always query `(metric_value_id == mv.id) OR (metric_id == metric.id AND metric_value_id IS NULL)`.

### 3.6 Frameworks (`models/frameworks.py`)

| Table | Purpose | Key columns | Constraints |
|---|---|---|---|
| `frameworks` | Registry (global; `tenant_id` NULL) | `code` (unique), `name`, `publisher`, `description`, `jurisdiction`, `industry`, `is_custom`, `tenant_id`? | |
| `framework_versions` | Versions | `framework_id` FK (cascade), `version`, `effective_date`, `status` (current, superseded, draft), `source_url`, `notes` | `uq_framework_versions_fw_version` |
| `requirements` | Disclosure requirements | `framework_version_id` FK, `parent_id` self-FK, `code`, `title`, `description`, `pillar`, `theme`, `disclosure_type` (quantitative, narrative, both), `evidence_required`, `is_core`, `applicability` JSON, `metric_codes` JSON, `sort_order`, `guidance` | `uq_requirements_fwv_code`, ix code |
| `framework_mappings` | Tenant-specific requirement ↔ metric mapping or omission | `requirement_id`, `metric_id`?, `mapping_type` (direct, partial, derived, narrative, omitted), `rationale`, `status` (proposed, approved, rejected), `confidence`, `created_by`, `omission_reason` | |
| `organization_frameworks` | Frameworks selected per organisation and period | `organization_id`, `framework_version_id`, `period_id`, `applicable_scope` JSON, `status` (active, assessment), `is_primary` | `uq_org_frameworks` |

### 3.7 Materiality (`models/materiality.py`)

| Table | Purpose | Key columns |
|---|---|---|
| `materiality_assessments` | Assessment per organisation/period | `name`, `methodology`, `approach` (impact, financial, double), `threshold` (default 3.0), `status`, `evidence_codes` JSON |
| `materiality_topics` | Topic scores | `assessment_id` FK (cascade), `topic_code`, `name`, `pillar`, `impact_severity`, `impact_likelihood`, `impact_score`, `financial_magnitude`, `financial_likelihood`, `financial_score`, `stakeholder_priority`, `is_material`, `rationale`, `related_metric_codes`, `related_requirement_codes`, `risks`, `opportunities`, `evidence_codes` |
| `stakeholder_inputs` | Stakeholder engagement inputs | `assessment_id` FK, `stakeholder_group`, `topic_code`, `priority`, `channel`, `concern`, `engagement_value` |

`impact_score = severity × likelihood / 5`, `financial_score = magnitude × likelihood / 5` (computed in the seeder and `PUT …/topics/{code}`).

### 3.8 Governance (`models/governance.py`)

| Table | Purpose | Key columns | Constraints |
|---|---|---|---|
| `governance_policies` | Policy documents | `code`, `name`, `category`, `description`, `owner`, `version`, `effective_date`, `status`, `evidence_code`, `external_ref` | `uq_policies_tenant_code` |
| `governance_rules` | Governance-as-code rules | `code`, `description`, `severity` (INFO…CRITICAL), `scope` (metric_value, report, ai_output, data_change, requirement), `condition`, `action` (`RULE_ACTIONS`), `message`, `required_action`, `owner`, `version`, `effective_date`, `approval_status` (draft, approved, retired), `is_active`, `params` JSON, `policy_code` | `uq_rules_tenant_code` |
| `issues` | Criticality-engine output | `code` (`ISS-00001`), `severity`, `category` (evidence_gap, data_missing, data_quality, inconsistency, framework_gap, governance, ai_quality, approval, target), `title`, `description`, `metric_code`, `entity_code`, `period_code`, `requirement_code`, `rule_code`, `status` (open, acknowledged, resolved, exception_approved), `required_action`, `blocks_report`, `resolved_by`, `resolution_note`, `resolved_at`, `fingerprint` | ix code, ix metric_code, ix fingerprint |
| `approvals` | Human-in-the-loop requests | `object_type` (metric_value, report_section, report, ai_output, exception, mapping), `object_id`, `state`, `requested_by`, `assigned_to`, `decided_by`, `decision` (approved, rejected, changes_requested), `comment`, `decided_at`, `context` JSON | ix object_id |

### 3.9 AI, knowledge, evaluation (`models/ai.py`)

| Table | Purpose | Key columns | Constraints |
|---|---|---|---|
| `agents` | Agent catalogue (global, mirrored from the registry at seed time) | `code` (unique), `name`, `description`, `responsibilities` JSON, `tools` JSON, `expert_profile`, `version`, `is_active` | |
| `agent_runs` | One row per agent execution | `agent_code`, `user_id`, `task`, `input` JSON, `output` JSON, `status` (completed, failed, blocked, requires_review), `confidence`, `sources`, `tools_used`, `guardrail_result` JSON, `evaluation_id` FK?, `expert`, `provider`, `started_at`, `finished_at`, `latency_ms`, `error` | ix agent_code |
| `model_runs` | One row per LLM call | `agent_run_id` FK (cascade), `provider`, `model`, `purpose`, `prompt_tokens`, `completion_tokens`, `cache_read_tokens`, `latency_ms`, `status`, `error`, `created_at` | ix agent_run_id |
| `knowledge_documents` | RAG documents | `code`, `title`, `kind` (framework, policy, report, methodology, metric_definition, evidence, internal, regulation), `version`, `source_ref`, `freshness_date`, `permissions` JSON `{"roles": [...]}`, `status` (approved, draft, retired), `meta` JSON | `uq_knowledge_docs_tenant_code` |
| `knowledge_chunks` | Chunks | `document_id` FK (cascade), `chunk_index`, `text`, `meta` JSON, `embedding` JSON (NULL unless an embedding provider is configured) | ix document_id |
| `evaluations` | Evaluation records | `object_type` (agent_run, report_section, report, dataset, metric), `object_id`, `evaluator`, `dimension` (ai, data, esg, report), `scores` JSON, `overall`, `findings` JSON, `passed`, `created_at` | ix object_id |
| `quality_scores` | Data-quality result per value | `metric_id`, `entity_id`, `period_id`, seven dimension columns, `overall`, `explanation` JSON, `computed_at` | `uq_quality_scores_metric_entity_period` |

### 3.10 Reporting (`models/reporting.py`)

| Table | Purpose | Key columns | Constraints |
|---|---|---|---|
| `report_templates` | Template mirror of `reports/templates/*.yaml` | `code` (unique), `name`, `description`, `sections` JSON, `tenant_id`? | |
| `reports` | Report instance | `organization_id`, `period_id`, `template_code`, `title`, `framework_codes` JSON, `scope` JSON, `status` (`REPORT_STATES`: draft, ai_generated, validating, requires_review, reviewed, approved, published, blocked), `readiness` JSON, `validation_result` JSON, `created_by`, `approved_by`, `published_at`, `locked` | |
| `report_sections` | Sections | `report_id` FK (cascade), `code`, `title`, `sort_order`, `level`, `content_md`, `narrative_source` (ai, human, template, data), `status`, `metric_codes`, `evidence_codes`, `requirement_codes`, `tables` JSON, `charts` JSON, `evaluation_id`?, `agent_run_id`?, `approved_by`, `version`, `comments` JSON | `uq_report_sections_report_code` |
| `report_versions` | Generated files | `report_id`, `version`, `format` (pdf, docx, xlsx, csv, html), `storage_key`, `file_hash`, `size_bytes`, `generated_by`, `created_at`, `is_final` | ix report_id |

### 3.11 Audit and notifications (`models/audit.py`)

| Table | Purpose | Key columns |
|---|---|---|
| `audit_logs` | Append-only trail | `user_id`, `action` (e.g. `data.modify`, `report.approved`, `ai.copilot`), `object_type`, `object_id`, `old_value` JSON, `new_value` JSON, `reason`, `ip`, `created_at`; indexes on user_id, action, object_type, object_id, created_at |
| `notifications` | In-app notifications | `user_id`? (NULL = broadcast), `kind`, `title`, `body`, `link`, `is_read`, `created_at` |

`core/audit.py::record` is the only writer; there is no update/delete API.

---

## 4. Key constraints and invariants

- **One value per (metric, entity, period)** — `uq_metric_values_metric_entity_period`. The ingestion pipeline, metric engine and seeder all upsert against this key.
- **One quality score per value** — `uq_quality_scores_metric_entity_period`.
- **One formula version per (metric, version)**; exactly one row should have `is_current=True` (enforced procedurally in `POST /metrics/{code}/formula`, not by a constraint).
- **Reported values are never overwritten by calculation** (`metric_engine.calculate`), and approved/final reported values are not overwritten by ingestion (`IngestionPipeline.load`).
- **Cascade deletes** flow from `organizations → entities/periods`, `metric_definitions → values/versions/runs/targets`, `datasets → versions → records`, `evidence → links`, `framework_versions → requirements`, `reports → sections/versions`, `agent_runs → model_runs`, `knowledge_documents → chunks`.
- **Issue fingerprint** deduplicates issues across rule runs; stale `evidence_gap`/`data_missing` issues are auto-resolved.

---

## 5. Tenant isolation

Every tenant-scoped query filters on `tenant_id == principal.tenant_id` (routers via `deps.get_org/get_metric`, tools via `ToolContext`, engines receive `tenant_id` explicitly). Objects reached through a parent (values, sections, records) are checked through the parent's tenant (`ReportBuilder.report`, `dataset_detail`, `records`). Global registries (frameworks, agents, templates) are shared read-only across tenants; `frameworks.tenant_id` and `report_templates.tenant_id` are reserved for tenant-specific custom entries.

Entity-level scoping: `user_roles.entity_id` populates `Principal.entity_ids`; `deps.get_entity` and `ToolContext.entity` raise 403 / `PermissionError` when the requested entity is outside the principal's scope (the seeded contributor is limited to EFERT).

See [SECURITY.md](SECURITY.md).

---

## 6. Migrations (Alembic)

- `backend/alembic.ini` — `script_location = alembic`, `prepend_sys_path = .`, file template `YYYYMMDD_<rev>_<slug>`.
- `backend/alembic/env.py` — sets `sqlalchemy.url` from `get_settings().database_url`, imports `app.models` so `Base.metadata` is complete, `compare_type=True`, `render_as_batch` on SQLite (ALTER TABLE emulation).
- `backend/alembic/versions/20260904_5f7f01feec2c_initial_schema.py` — the initial revision (all 45 tables, indexes and unique constraints). The Docker `CMD` runs `alembic upgrade head`; `development`/`test` environments additionally run `Base.metadata.create_all` at startup.

Creating the initial revision:

```bash
cd backend
ESG_DATABASE_URL=postgresql+psycopg://esg:pw@localhost:5432/esg_nexus alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Subsequent schema changes: edit the model, `alembic revision --autogenerate -m "<change>"`, review the script (JSON columns and SQLite batch mode in particular), `alembic upgrade head`. Downgrades are generated but should be reviewed for data-loss operations.

---

## 7. Seeding

`app/seed/loader.py::Seeder.run()` is idempotent (`_get_or_create` on natural keys) and runs at startup when `ESG_AUTO_SEED=true` and the `ecorp` tenant or any metric value is missing (`seed_if_needed`). Order: tenant/roles/users → organisation/periods/entities → topics → frameworks (YAML) → source document → metrics and values (page evidence created on first reference) → data sources and dataset versions (reported values attached per pillar) → targets → materiality → governance → organisation-framework selections → approved omissions → knowledge base (5 documents) → agents → templates → commit → recompute (calculations, quality, rules for FY2022 and FY2023). `POST /admin/reseed` (super_admin) re-runs it.
