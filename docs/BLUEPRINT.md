# ESG Nexus — Implementation Blueprint

**Enterprise ESG Intelligence, Governance & Reporting Platform**

This blueprint is the design produced before implementation. It is the reference
that every module in this repository implements. Sections A–W follow the required order.

Reference dataset: the Engro Corporation Limited *Sustainability Report 2023* (public document,
80 PDF pages, reporting period 1 Jan 2023 – 31 Dec 2023, aligned with WEF Stakeholder Capitalism
Metrics, UN SDGs and UNGC, ISAE 3000 limited assurance). Every quantitative and qualitative
disclosure in that document is modelled as a governed metric with page-level evidence lineage.

---

## A. Product vision

ESG Nexus is the organisation's **ESG system of record**. It manages the full lifecycle

`Data → Validation → Calculation → Evidence → Governance → Standards Mapping → Analysis → Evaluation → Assurance → Visualization → Report Generation`

for multi-entity groups (holding company → subsidiaries → business units → facilities). It is not a
dashboard: it is an operating platform whose outputs (metrics, narratives, reports) are traceable,
explainable, evidence-backed and auditable. Deterministic engines compute every number; AI assists
with classification, extraction, mapping, reasoning, narrative drafting and anomaly detection, and
every AI output passes validation → evaluation → governance → human approval before it can be used.

Non-negotiable principles:

1. No fabricated ESG data. Missing data returns `Data unavailable` / `Evidence required` / `Human review required`.
2. No "compliance" claims. The platform reports *Framework Alignment*, *Disclosure Coverage*, *Evidence Coverage*, *Reporting Readiness* and *Gap Analysis*.
3. Every reported value resolves to `Report Metric → Calculated Value → Formula → Inputs → Source Dataset → Original Source → Evidence`.

## B. User personas

| Persona | Goal | Primary surfaces |
|---|---|---|
| Chief Sustainability Officer / Executive | "Are we ready to publish? Where are the risks?" | Executive dashboard, readiness, materiality, report preview |
| ESG Manager | Owns the reporting cycle, targets, approvals | KPI tracking, standards gaps, approvals, report builder |
| ESG Analyst | Prepares data, runs calculations, fixes quality issues | Datasets, data quality, metric detail, lineage, copilot |
| Data Contributor (plant / HR / finance) | Uploads source data and evidence | Data sources, ingestion, evidence upload |
| Reviewer / Report Approver | Reviews AI narratives and sections, approves | Approvals, report preview, audit trail |
| Auditor / Assurance provider | Verifies evidence packages and lineage | Evidence repository, audit trail, assurance package export |
| Organisation Admin / Super Admin | Tenancy, users, roles, taxonomy, frameworks, rules | Administration, governance rules |

## C. User journeys

1. **Reporting-cycle setup** — Admin creates organisation hierarchy, reporting period FY2023, selects frameworks (WEF SCM Core, UNGC, UN SDGs; optionally GRI/IFRS S1-S2/ESRS/SASB).
2. **Data intake** — Contributor uploads CSV/Excel/JSON or the source PDF; the ingestion pipeline records source, version, validation result; the ESG Data Agent proposes field→metric mappings; analyst confirms.
3. **Calculation** — Metric Engine evaluates derived metrics (TRIR, turnover rate, renewable share, intensities, YoY) with versioned formulas; lineage graph is recorded.
4. **Quality & governance** — Data Quality Engine scores each metric (completeness, accuracy, consistency, timeliness, validity, uniqueness, traceability); Governance rules raise issues (e.g. Scope 1 without evidence → CRITICAL, blocks report).
5. **Standards mapping** — Framework engine computes applicable / completed / missing requirements, evidence gaps, narrative gaps and alignment %.
6. **Materiality** — Impact × financial scoring per topic, stakeholder inputs, matrix.
7. **AI assistance** — Copilot answers grounded questions with sources; Reporting Agent drafts sections; Evaluation Agent scores factuality/groundedness/citations; Governance Agent gates.
8. **Review & approval** — Draft → AI Generated → Validating → Requires Review → Reviewed → Approved → Published, with role-gated transitions and audit trail.
9. **Report generation** — Pre-generation validation (9 checks); blocked with explicit reasons if critical issues exist; PDF/DOCX/XLSX/CSV export.

## D. Feature map

- ESG Intelligence: Overview, Environment, Social, Governance, Prosperity dashboards; metric drill-down.
- Data: sources, datasets & versions, ingestion, data quality, lineage.
- Metrics: library, KPI tracking, calculations (versioned), targets.
- Standards: framework registry (config-driven), requirements, mapping, alignment & gaps.
- Materiality: assessment, interactive matrix.
- Evidence: repository, metric ↔ evidence links, gaps, integrity hashes.
- AI: agents, agent runs, knowledge base, RAG, evaluation centre, copilot.
- Governance: policies, governance-as-code rules, approvals, audit trail, issues / criticality.
- Reports: builder, preview, validation, generation, generated reports.
- Administration: organisation, users, roles, system configuration, health.

## E. System architecture

```
React/TS SPA ──► Nginx ──► FastAPI (API gateway + app services)
                              │
                ┌─────────────┼──────────────────┐
                ▼             ▼                  ▼
        Domain services   Engines            AI orchestration
        (bounded ctx)     metric/quality/    agents · MoE router ·
                          lineage/rules/     RAG · guardrails ·
                          readiness          evaluation
                │             │                  │
                └─────────────┼──────────────────┘
                              ▼
        PostgreSQL (+pgvector) · Redis (cache/queue) · S3-compatible object store
```

Backend follows Clean Architecture: `api/` (transport) → `services/` (application) → `engines/` +
`ai/` (domain logic) → `models/` (persistence). Bounded contexts: identity, organization, esg_data,
metrics, frameworks, materiality, evidence, governance, ai, evaluation, reporting, audit,
notifications, administration.

## F. Database architecture

PostgreSQL, normalised. Core entities (see `docs/DATABASE.md` for the ERD):

`tenants, users, roles, user_roles, organizations, entities (subsidiary/business_unit/facility, self-referencing tree), reporting_periods, esg_topics, esg_subtopics, metric_definitions, metric_values, data_sources, datasets, dataset_versions, dataset_records, evidence, evidence_links, frameworks, framework_versions, requirements, framework_mappings, materiality_assessments, materiality_topics, targets, calculations, calculation_versions, calculation_runs, lineage_nodes, lineage_edges, governance_policies, governance_rules, issues, agents, agent_runs, model_runs, evaluations, knowledge_documents, knowledge_chunks, reports, report_sections, report_versions, approvals, audit_logs, notifications, quality_scores`.

All tenant-scoped tables carry `tenant_id`; queries are filtered by the caller's tenant. Migrations via Alembic.

## G. API architecture

Versioned REST under `/api/v1/*` with OpenAPI, Pydantic validation, JWT auth, RBAC dependencies,
pagination (`limit/offset`), filtering, sorting, consistent error envelope
`{"error": {"code", "message", "details"}}`, idempotency keys on ingestion and report generation.

Routers: `auth, organizations, esg, metrics, datasets, quality, lineage, evidence, frameworks,
materiality, governance, agents, copilot, evaluations, reports, audit, admin, health`.

## H. AI architecture

`LLMProvider` abstraction (`AnthropicProvider` using the official `anthropic` SDK with
`claude-opus-5`, adaptive thinking, structured outputs; `OfflineProvider` deterministic
template-based fallback so the platform runs air-gapped). Agents never touch the database directly:
they call **controlled tools** (`get_metric`, `get_metric_history`, `get_dataset`, `get_evidence`,
`get_framework_requirement`, `get_framework_mapping`, `calculate_metric`, `run_data_quality_check`,
`run_governance_check`, `search_knowledge_base`, `generate_report_section`, `evaluate_output`) which
enforce tenant + permission scoping. Every model call is logged as a `model_run` with token usage.

## I. Multi-agent architecture

Specialised agents, each a class with declared tools, system prompt, input/output schema:
ESG Data Agent, Calculation Agent (explains; never computes), Standards Mapping Agent, Materiality
Agent, Evidence Agent, Governance Agent, RAG Research Agent, Reporting Agent, Evaluation Agent,
Assurance Agent. An `AgentRegistry` allows new agents to be registered without touching the core.

## J. Mixture-of-Experts

`ExpertRouter` classifies a task (rule + LLM classification) and routes to one or more experts
(ESG, Climate, GHG, Financial Reporting, Governance, Risk, Legal/Compliance, Data Quality,
Statistics, Document Intelligence, Report Writing). Each expert is a prompt/tool profile; responses are
validated and aggregated. Never fan-out to every expert.

## K. Agentic RAG

Knowledge sources: framework definitions, metric definitions, calculation methodologies, policies,
historical reports (the 2023 report is ingested page-by-page), evidence. Pipeline: chunk → index
(lexical BM25 in-process by default; `PgVectorIndex` adapter when embeddings are configured) →
permission filter → rerank → cite. Every answer exposes sources, confidence and freshness.

## L. Governance-as-Code

Rules are data: `{rule_id, description, severity, condition, action, owner, version, effective_date, approval_status}`.
Conditions are a small safe expression language over a context (`metric`, `value`, `evidence_count`,
`quality_score`, `ai_confidence`, `report.status`, …). Actions: `BLOCK`, `WARN`, `ESCALATE`,
`REQUIRE_APPROVAL`, `REQUIRE_EVIDENCE`, `REQUIRE_HUMAN_REVIEW`, `PREVENT_DATA_MODIFICATION`,
`BLOCK_REPORT_GENERATION`. The rules engine runs on data change, before AI outputs are accepted, and
before report generation.

## M. Guardrails

Input: prompt-injection patterns, unsupported formats, sensitive data patterns, out-of-range ESG
values, malformed data. Output: unsupported numeric claims (every number in a narrative must match a
governed metric), missing citations, framework mismatch, policy violations, confidentiality leakage.
Raw model output never becomes a disclosure.

## N. Evaluation architecture

Evaluation Centre scores Data Quality, AI Quality (factuality, groundedness, relevance, citation
correctness, numerical consistency, hallucination rate), ESG Quality (framework alignment,
disclosure completeness, evidence coverage, metric coverage) and Report Quality. Scores are stored
per run and tracked over time; an eval dataset (`backend/tests/ai_evals`) protects against regressions.

## O. Security architecture

JWT auth (OIDC-ready), RBAC with 9 roles, tenant isolation on every query, dataset/document/evidence
permissions, audit logs, secrets via environment, rate limiting middleware, input/output validation,
password hashing (PBKDF2-SHA256), CORS, security headers.

## P. Visualization architecture

Left navigation. Every domain page: KPI cards → trend → comparison → risk → evidence →
underlying data. Charts: trend, comparison, target vs actual, YoY, distribution, heatmap, waterfall,
Sankey (energy/wealth flows). Every chart click → drill-down → source data → evidence. Period
switcher (year/quarter/custom).

## Q. Report-generation architecture

Pipeline: validated metrics → framework requirements → disclosure mapping → approved evidence →
narrative generation → AI evaluation → governance check → human review → assembly → final
validation → PDF/DOCX/XLSX/CSV. Templates are YAML section definitions; sections are dynamic based on
the selected frameworks and applicability. Nine pre-generation checks; critical failures block generation
with explicit reasons and required actions.

## R. Deployment architecture

Docker images for `backend` and `frontend`; `docker-compose.yml` with PostgreSQL (pgvector image),
Redis, MinIO, backend, worker, frontend/Nginx. Health checks, env-driven config, Kubernetes-ready
(stateless services, 12-factor). Observability: structured JSON logs, request metrics, health endpoints,
model/agent latency and token usage recorded in `model_runs`.

## S. Folder structure

```
esg-nexus/
  backend/app/{core,models,schemas,services,engines,ai,ingestion,reports,api/v1,seed}
  backend/tests/
  backend/alembic/
  frontend/src/{app,api,components,features,lib}
  frameworks/*.yaml          # configuration-driven frameworks
  seed/ecorp_2023/*.yaml     # reference dataset derived from the 2023 report
  docs/                      # architecture, DB, API, agents, RAG, governance, security, deployment, guides
  docker-compose.yml, Makefile, .env.example
```

## T. Development roadmap

Phases 1–10. This repository delivers a modular vertical slice of every phase: foundation,
data pipeline, ESG domains, frameworks, evidence, AI, governance, evaluation, reporting and enterprise
scaffolding (multi-tenancy, security, observability, containers).

## U. Testing strategy

Unit (engines, rules DSL, formula evaluator), calculation golden tests (known inputs → expected outputs
from the report, e.g. TRIR 0.09), API tests (FastAPI TestClient over SQLite), framework-mapping tests,
governance tests, guardrail tests, RAG retrieval tests, report generation tests, AI eval suite (offline
provider, deterministic).

## V. Documentation strategy

README, ARCHITECTURE, DATABASE, API, AGENTS, RAG, GOVERNANCE, SECURITY, DEPLOYMENT, ONBOARDING,
TESTING, FRAMEWORKS plus the mandatory how-to guides (metric, framework, agent, report section,
connector, governance rule).

## W. Extensibility strategy

Registries (metrics, formulas, frameworks, agents, experts, connectors, report sections, rules
actions), strategy/adapter patterns (LLM provider, vector index, object storage), configuration-driven
frameworks and templates, event hooks on data change, and domain-driven module boundaries so a new
standard, metric, agent or connector is an additive change.
