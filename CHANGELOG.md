# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [Unreleased]

## [1.0.0] - 2026-09-04

### Added
- Backend API (FastAPI): organisation hierarchy with consolidation, metric library and versioned calculation engine, data-quality engine, lineage, governance-as-code rules with issues and approvals, framework registry (WEF SCM, UNGC, UN SDGs, GRI, IFRS S1/S2, ESRS, SASB), materiality module, evidence repository with inheritance for derived values, ingestion pipeline (CSV, Excel, JSON, PDF), audit trail.
- AI layer: ten specialised agents over controlled tools, Mixture-of-Experts routing, permission-aware retrieval, input/output guardrails, deterministic evaluation, copilot; offline provider by default with an optional Anthropic provider.
- Report builder with AI-drafted sections, nine pre-generation checks, review/approval workflow and PDF/DOCX/XLSX/CSV/HTML output.
- Reference dataset: 479 metrics from the Engro Corporation Sustainability Report 2023 with page-level evidence.
- React + TypeScript frontend covering dashboards, metric drill-down, data, standards, materiality, evidence, AI, governance, reports and administration.
- Docker Compose stack, Alembic migrations, test suite, documentation set and CI/CD workflows.

[Unreleased]: https://github.com/RayyanAlam1/esg-nexus/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/RayyanAlam1/esg-nexus/releases/tag/v1.0.0
