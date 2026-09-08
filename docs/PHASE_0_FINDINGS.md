# Phase 0 — Research findings

Date: 2026-09-07 · Scope: the repository as of commit `292f331` on `main` · Status: complete, awaiting review

This document records what actually exists before anything is changed. Every statement below was verified against the code, the running application or a fetched source; nothing is inferred from the documentation alone. Sections:

1. [Method](#1-method)
2. [Current state, honestly assessed](#2-current-state-honestly-assessed)
3. [Test suite and coverage](#3-test-suite-and-coverage)
4. [Frontend walkthrough by role](#4-frontend-walkthrough-by-role)
5. [UI ↔ API coverage](#5-ui--api-coverage)
6. [Documentation versus code](#6-documentation-versus-code)
7. [Design reference decisions](#7-design-reference-decisions)
8. [Risk register ranked by launch impact](#8-risk-register-ranked-by-launch-impact)
9. [What this means for Phase 1](#9-what-this-means-for-phase-1)

Evidence screenshots referenced below are in [`docs/phase0/`](phase0/).

---

## 1. Method

| Activity | How it was done |
|---|---|
| Repository read | Every file under `docs/`, `README.md`, all 20 routers in `backend/app/api/v1`, engines, models, builder, worker, storage paths; all 90 frontend source files |
| Tests | `pytest --cov=app` in the project venv (Python 3.14.6) |
| Application run | Backend on `:8000` (SQLite, offline AI provider, auto-seed), Vite dev server on `:5173` |
| Role walkthrough | Scripted browser crawl (Playwright/Chromium, 1440×900) of all 42 routes for each of the 8 seeded users, capturing screenshots, console errors, failed requests, row counts and load time; then manual interactive flows (report builder, copilot, upload, metric tabs, approvals) as manager, contributor, reviewer, approver and auditor; mobile viewport check at 390×844 |
| API coverage | Static cross-reference of every backend route against `frontend/src/api/*.ts` and every call site in `frontend/src/features/**` |
| Design references | Computed styles captured live from github.com, linear.app and vercel.com; design-system documentation fetched from Primer (GitHub), Geist (Vercel), Polaris (Shopify), Atlassian and Material 3 token sources; Stripe's colour-system article; Linear's redesign write-up |

---

## 2. Current state, honestly assessed

### 2.1 What is genuinely solid

- **Domain model and engines.** 45 tables, a single Alembic revision that matches the models (`alembic check` is clean), a safe AST-whitelisted formula evaluator, topologically ordered recalculation that never overwrites reported values, seven-dimension data quality, on-demand lineage, a governance rules DSL with 15 seeded rules, evidence inheritance for derived and consolidated values, and readiness scoring. These behave as documented and are exercised by the tests.
- **Reference dataset.** 479 metric definitions, 633 numeric and 66 narrative values, every value cited to a printed page of the source report, with the report's own internal inconsistencies surfaced as quality findings rather than silently corrected. This is the product's credibility and it holds up.
- **AI layer discipline.** Deterministic engines compute; agents only explain, map and draft over controlled tools; every output passes input guardrail → tools → provider → output guardrail → evaluation → governance → persisted run. The copilot answered a scoped question in 1.4 s with sources, metrics used, evidence, expert routing, guardrail and evaluation outcomes visible ([10-copilot.png](phase0/10-copilot.png)).
- **Language discipline.** "Alignment, not compliance" is consistently applied in API responses, UI copy and the report renderers.
- **Breadth of the frontend.** 47 feature files, 44 routed pages, no placeholder screens, no UI call that hits a missing endpoint, 79 % of the API surface reachable.

### 2.2 What is not

- **The product experience is a competent internal tool, not an enterprise product.** Visual design is a default Tailwind palette (teal sidebar, grey cards), system font, no elevation system, no motion, no dark mode, no density control. Tables are the weakest part: the Metric Library wraps names into five-line cells because the code column is fixed-width ([02-metric-library.png](phase0/02-metric-library.png)); Data Quality squeezes the explanation column into a 60-px strip ([03-data-quality.png](phase0/03-data-quality.png)); Issues pushes the date column off-screen ([04-issues.png](phase0/04-issues.png)).
- **Three functional defects were found in core flows** (details in §4.3): the report preview page crashes for every role once a report has been validated; the report builder opens with an unusable "FY2021 (closed)" period and a disabled Next button; entity-scoped users see an endless skeleton instead of a scoped dashboard.
- **The security posture is not deployable to a second customer.** Cross-tenant issue leaks, a default JWT secret that is never rejected, a demo super-admin seeded on first boot, a path-traversal write in evidence upload, and no tenant or user lifecycle APIs (§8).
- **The documentation is candid about its limits but overstates in places** — "tenant isolation on every query", "entity scoping enforced", "EmailStr", and a `TESTING.md` that describes test files which do not exist (§6).
- **Nothing in the request path is asynchronous.** Every value write triggers a full recalculation of all formula metrics across all entities; report drafting and validation run inline; seeding runs in the lifespan of every worker process.

### 2.3 Numbers that frame the work

| Measure | Value |
|---|---|
| Backend routes / reachable from UI | 116 / 92 (79 %) |
| Frontend routed pages / placeholder pages | 44 / 0 |
| Tests / passing / runtime | 46 / 46 / 66.7 s |
| Statement coverage | 77 % (6,195 statements) |
| Routes that crash a role | 1 (`/reports/:id/preview`, every role) |
| Routes that hang for a scoped user | 7 (dashboard, ESG overview, four pillar pages, metric detail) |
| Pages slower than 2.5 s on first load (warm SQLite, admin) | 5 (dashboard 3.7 s, ESG overview 3.3 s, social 4.9 s, environment 2.7 s, evaluation 2.9 s) |
| Launch-blocking risks | 6 (§8) |
| Findings withdrawn after closer reading | 1 (risk 17, §8) |

---

## 3. Test suite and coverage

**Result:** 46 passed, 0 failed, 0 skipped in 66.7 s. Overall coverage 77 %. Slowest test: the end-to-end report workflow at 45.6 s; the seed fixture takes 12 s.

**Zero-coverage modules:** `app/worker.py` (queue consumer) and `app/ai/llm/anthropic_provider.py` (the only non-offline provider).

**Lowest-coverage areas:** `api/v1/evidence.py` 33 %, `api/v1/datasets.py` 43 %, `ai/agents/specialists.py` 43 %, `api/v1/frameworks.py` 48 %, `api/v1/governance.py` 48 %, `ingestion/connectors.py` 55 %, `api/v1/metrics.py` 55 %.

**Behaviours with no test at all:**

- Ingestion connectors other than CSV (JSON, Excel, PDF, text), idempotency keys, explicit version load, classification.
- Renderer content (PDF/DOCX/XLSX/CSV are only checked for size > 1 kB; HTML renderer untested).
- Worker queue and scheduled modes.
- Consolidation methods other than `full` (proportional, avg, weighted_avg, max, last) and grand-child recursion.
- Rate limiting, token expiry, tampered signatures, refresh flow, inactive users.
- **Cross-tenant isolation: the suite seeds exactly one tenant, so no isolation assertion exists.**
- Entity scoping on list endpoints, ingestion, evidence, targets.
- Report transitions other than the happy path (rejection, backwards moves, `locked` enforcement, final generation on unapproved reports).
- Governance, admin, evidence and frameworks API surfaces.
- PostgreSQL: CI applies migrations to SQLite only; the `psycopg` path has never run in CI.

---

## 4. Frontend walkthrough by role

### 4.1 What each role can reach

All eight users log in. Navigation gating is by capability and matches the route guards in `App.tsx`:

| Role | Hidden from navigation | Notes |
|---|---|---|
| super_admin + org_admin | nothing (39 items) | full access |
| executive | Administration, Report Builder | can view every operational screen |
| esg_manager | Administration | only role besides admin that can build reports |
| esg_analyst | Administration, Audit Trail | |
| data_contributor (EFERT-scoped) | Administration, Copilot, Audit Trail, Report Builder | **dashboard and metric detail hang** (§4.3) |
| reviewer | Administration, Report Builder | |
| report_approver | Administration, Copilot, Report Builder | approver cannot use the copilot |
| auditor | Administration, Copilot, Report Builder | can read evidence detail with hash, page reference and verification state |

Direct navigation to a gated route renders a plain "Not authorised — your roles do not include the capability `admin`" card inside the shell. It is correct but exposes the internal capability name.

### 4.2 Screen-by-screen assessment (admin view)

Legend: **OK** works and is acceptable · **Weak** works but below the bar · **Broken** defect

| Area | Screen | Verdict | Observations |
|---|---|---|---|
| Overview | Dashboard | Weak | Readiness ring + seven bars and 12 KPI cards render real data. Yellow "TARGET NOT SET" chips dominate the cards; the quality/evidence chips (`2 · Q 100`) are unexplained glyph clusters; 3.7 s first load ([01](phase0/01-dashboard-admin.png)) |
| ESG Intelligence | Overview, four pillars | Weak | Complete and data-rich (Social renders 23 metrics, 4 charts). Trend charts plot two points on an axis that also shows FY2021 and FY2024 with no data; entity comparison is one bar; 4.9 s load on Social |
| Data | Sources, Datasets, Dataset detail | OK | Upload dialog has file, code, name, source, default entity/period, auto-load toggle and a "Classify columns with ESG Data Agent" action |
| Data | Data Quality | Weak | Ring, pillar bars, lowest-scoring list, 50-row table. Explanation column unreadable; the "lowest-scoring" card clips its last item ([03](phase0/03-data-quality.png)) |
| Data | Lineage | OK | Empty state until a metric is chosen; graph renders on selection |
| Metrics | Library | Weak | Search + four filters + sortable table; row heights of 100–140 px because the name column is starved ([02](phase0/02-metric-library.png)) |
| Metrics | KPI tracking, Calculations, Targets | OK | Calculations lists 58 formulas with versions; Targets shows 12 with `not_set` gaps |
| Metrics | Metric detail | Weak | Six summary tiles, trend, nine tabs (calculation, inputs, evidence, mapping, quality, AI analysis, governance, audit, lineage) all load real data. "Approve" / "Back to draft" workflow buttons sit in the trend card header; no explanation of what they act on ([05](phase0/05-metric-detail.png)) |
| Standards | Frameworks, Requirements, Mapping, Compliance | OK | Compliance page carries the alignment disclaimer twice; requirement table with status/gap chips is the best table in the app |
| Materiality | Assessment, Matrix | OK | Double-materiality scatter with threshold lines; topic panel edits scores |
| Evidence | Repository, Gaps, Detail | OK | 125 items, SHA-256, page reference, verify action; Gaps shows 0 gaps and 8 unverified items |
| AI | Agents, Runs, Run detail, Knowledge, RAG search, Evaluation, Copilot | OK | Ten agent cards with tool chips and run counts; copilot answer carries provenance |
| Governance | Policies, Rules, Approvals, Issues, Audit | Weak | Issues: 51 open (18 medium, 33 low), acknowledge/resolve/exception actions; the table's last column is cut to 3 characters ([04](phase0/04-issues.png)). Approvals is empty in the seed, so the approval UI has never been seen with data |
| Reports | List, Builder, Preview | **Broken** | See §4.3 |
| Admin | Organization, Users, Roles, System | OK | System page shows host filesystem paths to any admin |

### 4.3 Defects found

1. **Report preview crashes for every role.** `/reports/:id/preview` renders a loading skeleton forever ([07](phase0/07-report-preview-crash.png)). The console shows an uncaught React error, "Objects are not valid as a React child", thrown by `ValidationChecks` in `frontend/src/features/reports/ReportBuilderPage.tsx`. Cause: once a report has been validated, the backend's `governance_validation` check returns `detail` as a list of objects (`[{rule: "GR-022", message: …}]`) and `reason` as a nested list, while the component renders `{c.detail}` and `{r}` as text. There is no error boundary anywhere in the frontend (`grep ErrorBoundary` finds nothing), so the whole page dies silently. This blocks section review, approval, transitions and file generation from the UI — the entire "human review" half of the product.
2. **Report builder opens unusable.** Step 1 shows "FY2021 · FY 2021 (closed)" in the select while the component state holds no period, so Next is disabled with no message ([06](phase0/06-report-builder-step1.png)). The select's displayed value and its state disagree because the header period is loaded asynchronously and the wizard copies it once on mount.
3. **Entity-scoped users hang.** The EFERT-scoped contributor gets HTTP 403 from `/esg/overview`, the four pillar endpoints, `/metrics/kpis` and `/metrics/{code}/detail` because the UI defaults the entity selector to the group entity ECORP, which is outside their scope. The pages render the loading skeleton indefinitely instead of an error or a scoped view ([08](phase0/08-contributor-dashboard.png)). The entity selector still lists all 25 entities for this user.
4. **Mobile is unusable.** At 390 px the sidebar occupies the full width and the document scrolls horizontally to 776 px ([09](phase0/09-mobile.png)). Not a pilot blocker for a desktop product, but tablets are common for site data contributors.
5. **Reports list rows are not links.** Rows navigate on click but render no anchor, so there is no hover affordance, no middle-click, no keyboard access.
6. **Login page prints demo passwords** for all eight accounts (`LoginPage.tsx` lines 6–12). Fine for the demo, must not ship.

### 4.4 Performance observations

Warm SQLite, single user: dashboard 3.7 s, ESG overview 3.3 s, Social pillar 4.9 s. The pillar pages issue one request per topic card and per chart in a waterfall; the overview endpoint recomputes readiness (which runs `recalculate_all`) on every call. Every value write in the API triggers a full recalculation (about 1,450 formula evaluations with the seed) plus quality assessment plus rule evaluation synchronously.

---

## 5. UI ↔ API coverage

116 routes (114 under `/api/v1` plus two health probes). 92 are reachable from a screen. No frontend call targets a non-existent route or sends mismatched fields. Per router:

| Router | Reached / total | Unreachable endpoints |
|---|---|---|
| auth | 1 / 3 | `GET /auth/me` (function exists, unused), `POST /auth/refresh` (the client never refreshes; on 401 it logs out) |
| organizations | 2 / 6 | list entities, list periods (unused functions); `POST` entities, `POST` periods (no UI to create structure) |
| esg | 4 / 4 | — |
| metrics | 5 / 12 | `GET /metrics/{code}` , `POST /metrics/{code}/calculate` (unused functions); `POST /metrics` (create definition), `GET …/values`, `POST …/formula` (new formula version), `GET …/lineage`, `GET …/runs` |
| targets, calculations, quality, lineage, audit, copilot, knowledge, admin, health | all reached | — |
| datasets | 7 / 8 | `POST /datasets/sources` (create a data source) |
| evidence | 7 / 8 | `POST /evidence/upload` (file upload — the UI only registers evidence as JSON metadata) |
| frameworks | 8 / 10 | `POST /frameworks/reload`, `GET /frameworks/requirements/{code}` |
| materiality | 4 / 5 | `POST …/stakeholders` (function exists, unused) |
| governance | 12 / 14 | `POST /governance/policies`, `POST /governance/approvals` (request an approval — function exists, unused) |
| agents | 4 / 5 | `GET /agents/tools` (function exists, unused) |
| evaluations | 3 / 4 | `GET /evaluations/readiness` |
| reports | 12 / 14 | `GET …/versions` (function exists, unused), `GET …/preview.html` |

What the gaps mean for a pilot customer: there is **no UI to create or edit a metric definition, a formula version, a data source, an entity, a period or a policy**, no evidence file upload, no way to request an approval, and no in-app way to compare formula versions or calculation runs. A customer therefore cannot onboard their own catalogue without API calls or YAML edits.

Two minor findings: `GET /api/v1/evidence/kinds` has no auth dependency (publicly reachable); the health probes are fetched with a bare `fetch('/health')` that bypasses `VITE_API_BASE`.

---

## 6. Documentation versus code

The README's "Status and known limits" section is accurate. The following claims are not:

| Claim | Reality |
|---|---|
| "tenant isolation on every query" (BLUEPRINT, SECURITY, DATABASE) | `api/v1/esg.py:49` and `api/v1/metrics.py:235` query `Issue` by metric code without a tenant filter; login (`auth.py:43`) looks users up by email across tenants |
| "entity scoping is enforced on lookups and tools" (README, SECURITY) | True for `get_entity` and tools; `IngestionPipeline.load` writes values for any entity, and the test suite demonstrates the bypass; list endpoints for values, targets, quality, evidence, records, reports and audit are tenant-wide |
| "immutable / append-only audit trail" | Append-only by convention only; `ip` is never populated; failed logins, reads and downloads are not audited |
| `EmailStr` validation | Hand-written validator; `email-validator` is installed but unused |
| "stack traces are never returned; 5xx are logged with stack info by structlog" | No generic exception handler; unhandled errors return Starlette's plain-text 500 outside the error envelope, without the request id |
| `/health/ready` returns 200 when degraded (DEPLOYMENT) | Returns 503 |
| `redis` missing from requirements (DEPLOYMENT) | It is present |
| TESTING.md file list, AI-eval dataset, render assertions | Do not exist; the real files are `test_safe_expr.py`, `test_calculations.py`, `test_quality_rules_frameworks.py`, `test_ai.py`, `test_api.py` |
| BLUEPRINT presents lineage tables, LLM-based MoE routing, OIDC and event hooks as implemented | None exist; ARCHITECTURE.md correctly says so |
| README architecture diagram "tools registry (14)" | 15 tools |
| "Streaming" of AI drafts | SDK-internal only; nothing streams to the client |

Also stale: README:181 says no Alembic revisions are shipped (contradicted three paragraphs later), README:242 describes the frontend as "being built concurrently", ONBOARDING says Node 18+ while the frontend README says 20+ and CI uses 22.

---

## 7. Design reference decisions

### 7.1 What was measured

Computed styles captured from the live sites (desktop, dark theme where that is the default):

| | GitHub (Primer) | Linear | Vercel (Geist) |
|---|---|---|---|
| Font | Mona Sans VF → system stack | Inter Variable → SF Pro | Geist Sans / Geist Mono |
| Body | 14 px / 21 px (1.5), 400 | 15–16 px / 24 px, 400 | 16 px / 24 px, 400 |
| Meta / caption | 12 px / 18 px, muted `#9198a1` | 13 px, weight 510 | 14 px, muted `#8f8f8f` |
| List row title | 16 px / 24 px, 600 | — | — |
| Headings | title-medium 20 px | 40 px / 44 px, weight 590, letter-spacing −0.022 em | 40 px / 48 px, 600, letter-spacing −0.06 em |
| Radius | 3 / 6 / 12 px (small / medium / large) | pill 9999 px buttons | 4–6 px controls, 6 px base, 12 px modals |
| Borders | 1 px `#3d444d` on every flat surface | 1 px `#1c1c1f` | 1 px `rgba(255,255,255,0.14)` ring via shadow |
| Depth | resting `0 1px 1px, 0 1px 3px`; floating = ring + 6/12/18 px blur; large = ring + 24/48 px | surfaces lighten with elevation, shadows only when floating | 4 named shadow steps, each starting with a 1 px ring |
| Control height | 28 / 32 px | 32 px | 32 px |
| Counter / label | 12 px, 500, 20 px tall, 24 px radius | — | — |
| Motion | `--duration-fast` 80 ms; micro 100 / short 200 / medium 300 / long 500 ms (tokens) | 160 ms `cubic-bezier(.25,.46,.45,.94)` on buttons | hover transitions only |
| Neutrals | 14-step scale; bg `#0d1117`, muted `#151b23`, inset `#010409`, fg `#f0f6fc` / `#9198a1` | bg `#08090a`, fg `#f7f8f8` / `#8a8f98` | bg `#000` / `#0a0a0a`, gray 100–1000 in HSL, fg `#ededed` / `#a1a1a1` |

Documentation sources added: Atlassian `font.body` 14/20 and `font.metric` 28/32 & 24/28; Atlassian 8-px spacing tokens 2…80; Polaris table cell padding 6 px, `tabular-nums lining-nums` rule, sticky header shadow, 13/20 body; Primer DataTable 12 px / 20 px cells and condensed/normal/spacious padding 4/8/12 px; Material 3 duration tokens short 50–200, medium 250–400 and standard easing `(0.2, 0, 0, 1)`; Stripe's rule that text must sit ≥ 5 perceptual-lightness levels from its background (4.5:1) and icons ≥ 4 levels (3:1); Linear's move to LCH-generated palettes from three base variables plus a contrast parameter. The full extract with URLs is retained in the research notes.

### 7.2 Decisions for ESG Nexus (with rationale)

**Typography**
1. Body 14 px / 20 px, weight 400 — the intersection of GitHub, Atlassian and Polaris body sizes; dense governance screens need the smaller of the common choices.
2. Table cells 13 px / 20 px in the default density and 12 px / 20 px in condensed (Primer DataTable) so rows stay on the 4-px grid; headers 12 px medium, muted, no wrap.
3. Captions 12 px / 16 px. Headings 16/20 semibold (section), 20/24 semibold (page), 24/32 (report titles). Slight negative letter-spacing (−0.01 em) on 20 px and above, after Linear and Geist; none at body sizes.
4. KPI numerals 28/32 and 24/28 semibold with `font-variant-numeric: tabular-nums lining-nums`; the same on every numeric column, total, timestamp and hash. The current UI proportional-figures every number, which is why the dashboard tiles look uneven.
5. Font: Inter variable (self-hosted, subset) with the system fallback stack; `ui-monospace, SFMono-Regular, Menlo, Consolas` for codes, hashes and formulas. Inter is the closest widely-licensed match to Mona Sans/Geist; the current Segoe UI rendering is the single largest reason the app reads as generic.

**Spacing, sizing, radius**
6. 4-px grid, 8-px rhythm: 2, 4, 6, 8, 12, 16, 20, 24, 32, 40, 48, 64. Card padding 16; page gutter 16 → 24 at ≥ 1280 px; table cell padding 8×12 default, 4×8 condensed, 12×16 comfortable.
7. Control heights 28 (toolbar), 32 (default), 40 (forms and primary actions) — GitHub's control sizes.
8. Radii 4 (inputs, badges), 6 (buttons, cards), 12 (dialogs, popovers); 0 inside data grids.

**Depth**
9. Every flat surface gets a 1-px border; shadows are reserved for two levels: *raised* (`0 1px 1px, 0 1px 3px` at low alpha) for sticky headers and hover-lifted cards, *overlay* (1-px ring + 6/12/18-px blur) for menus, popovers, dialogs. This is exactly how GitHub and Vercel keep dense pages calm — borders do the structure, shadows only signal "floating".
10. Dark mode lightens surfaces per elevation instead of deepening shadows (Atlassian), with both themes generated from the same functional tokens (Primer).

**Colour**
11. A 12-step low-chroma neutral scale with role bands (bg default/muted/inset, border default/muted, fg default/muted/on-emphasis), generated in OKLCH so that Stripe's "level distance" rule guarantees contrast. Brand accent: a single teal retained from the current identity but re-tuned for 4.5:1 on both themes.
12. Semantic roles beyond success/attention/danger: workflow states *draft, in review, reviewed, approved, published, blocked* and data states *reported, calculated, consolidated, unavailable*, each with fg / muted bg / emphasis bg. Status is never colour-only; every badge carries a label or icon.
13. Chart palette derived from the same OKLCH scales at equal lightness so pillars remain distinguishable in dark mode and for colour-blind users.

**Motion**
14. 100 ms for hover, focus and colour; 150–200 ms for toggles, expand/collapse, row selection; 250–300 ms for drawers, dialogs and the copilot panel; nothing above 400 ms. Enter ease-out `(0.3, 0.8, 0.6, 1)`, exit ease-in, move `(0.2, 0, 0, 1)`.
15. **What never animates:** numeric values, table re-sorts and filters, chart data updates, audit rows, status badges, readiness scores. Loading dims content rather than animating skeleton shimmer over data that already exists. `prefers-reduced-motion` sets every duration to 0.
16. Where motion earns its place: page-level content fade-in on route change (150 ms), drawer/dialog slide, copilot answer reveal, expand/collapse of table rows and tree nodes, hover lift on interactive cards.

**Tables (the component that matters most here)**
17. Numbers right-aligned, text left, headers aligned with their data, never centred. 1-px dividers, no zebra by default, hover on pointer devices only, distinct selected state.
18. Column sizing driven by content type: code columns `max-content` in monospace, name columns flexible with a minimum, numeric columns fixed. Truncate with tooltip in list tables; wrap only in narrative cells.
19. Three densities (28 / 36 / 44-px rows) selectable per table and remembered; sticky header with muted background and raised shadow when stuck; sticky first column on wide grids; sortable headers are buttons with `aria-sort`; pagination above 50 rows with "21–40 of 142" copy; "—" for unavailable values, never blank.
20. Audit and evidence timestamps: relative under 7 days, absolute after, both tabular.

---

## 8. Risk register ranked by launch impact

One finding (17) was withdrawn on 2026-09-08 after reading the handler again during M0; it is kept in the table, struck through, rather than removed.

Rating scale: **Launch-blocking** — cannot go to a paying multi-tenant customer · **Pilot-fix** — a single-tenant pilot is tolerable with mitigations, must be fixed before general availability · **Defer** — v2.

| # | Risk | Where | Rating |
|---|---|---|---|
| 1 | `ESG_SECRET_KEY` defaults to `change-me-in-production` and nothing rejects it in production; `auto_seed` defaults on, so the first boot creates `admin@esgnexus.local / Admin!2024` as super-admin | `core/config.py:37,55`, `.env.example`, `docker-compose.yml` | Launch-blocking |
| 2 | Cross-tenant leak: `/metrics/{code}/detail` returns other tenants' issues; KPI cards count them; login resolves email across tenants non-deterministically | `api/v1/metrics.py:235`, `api/v1/esg.py:49`, `api/v1/auth.py:43` | Launch-blocking |
| 3 | No tenant or user lifecycle: no create-tenant, bootstrap admin, password change or reset, deactivate, logout; tenants exist only through the demo seeder | `api/v1/admin.py`, `seed/loader.py` | Launch-blocking |
| 4 | Path traversal on evidence upload: `code` and `filename` are concatenated into the storage path unsanitised; any `evidence.write` role can write outside the storage directory | `api/v1/evidence.py:188` | Launch-blocking |
| 5 | Storage: absolute host paths persisted as `storage_key`, evidence folder not tenant-partitioned (same code + filename overwrites another tenant's file while the hash still points at the original), breaks with two API replicas | `reports/builder.py:558-569`, `api/v1/evidence.py:185-198` | Launch-blocking |
| 6 | First-deploy races: every uvicorn worker and every replica runs seeding and `alembic upgrade head` concurrently in the lifespan/CMD | `main.py:33-37`, `Dockerfile` | Launch-blocking |
| 7 | Report preview page crash (§4.3 #1) — the review/approval UI is unusable | `frontend/.../ReportBuilderPage.tsx` `ValidationChecks`; backend `builder.py` mixes types in `detail`/`reason` | Launch-blocking for the product promise |
| 8 | Governance freeze bypass: report and section transitions ignore `locked` and state order; an analyst can move an approved report back to `requires_review`, which silently lifts rule GR-020's data freeze | `reports/builder.py:447-482`, `services/governance_service.py:86` | Pilot-fix |
| 9 | Entity scoping: ingestion writes and most list endpoints ignore `entity_ids`; scoped users get 403 + endless skeleton (§4.3 #3); `PUT /admin/users/{id}/roles` drops entity scope | `ingestion/pipeline.py:192-221`, `api/v1/admin.py:93` | Pilot-fix |
| 10 | Synchronous heavy work: full recalculation on every value write; draft, validate and final generation inline in one HTTP request (minutes with the Anthropic provider, behind a 60-s proxy default); no job id or progress | `api/v1/metrics.py:315`, `reports/builder.py` | Pilot-fix |
| 11 | Worker pops the job before executing (loss on crash), no retry, exits on the first non-import exception, no restart policy | `worker.py` | Pilot-fix |
| 12 | Auth hardening: non-rotating 14-day refresh tokens, no revocation, in-process rate limit keyed on `request.client.host` (one bucket behind a proxy), no login-specific limit, unbounded bucket growth | `api/v1/auth.py:57`, `main.py:62-69` | Pilot-fix |
| 13 | PostgreSQL never exercised: CI migrates SQLite only; `String(64)` audit `object_id` and `String(300)` `storage_key` will fail on long values; `LIKE` case semantics differ | `.github/workflows/ci.yml`, `models/audit.py:16` | Pilot-fix |
| 14 | No generic exception handler (500s escape the envelope and skip security headers), no error tracking, audit `ip` never populated, `x-request-id` accepted unvalidated | `core/errors.py`, `main.py` | Pilot-fix |
| 15 | `POST /frameworks/reload` (any `esg_manager`) rewrites the global framework registry for all tenants; `POST /admin/reseed` re-creates the demo tenant in any deployment | `api/v1/frameworks.py:98`, `api/v1/admin.py:143` | Pilot-fix |
| 16 | Report-version race: no unique constraint on `(report_id, version)`; concurrent generates duplicate version numbers | `models/reporting.py` | Pilot-fix |
| 17 | ~~Issue severity ordering is alphabetical~~ **Withdrawn 2026-09-08.** The SQL `ORDER BY` is alphabetical but the handler re-sorts by severity rank in Python immediately afterwards, before any slicing, so the displayed order is correct. Recorded here rather than deleted, because a withdrawn finding is part of an honest audit trail. | `api/v1/esg.py:106-111` | Not a defect |
| 18 | No UI for catalogue authoring (§5): metric definitions, formulas, sources, entities, periods, policies, evidence files | frontend | Pilot-fix |
| 19 | Vector search stub: BM25 works air-gapped and is honestly documented; index cache invalidates on chunk count only | `ai/rag/index.py` | Defer |
| 20 | Mobile layout | frontend | Defer (desktop product) |

The README's four named limits map as follows: vector search → Defer; lightweight worker → Pilot-fix (with the seeding race carved out as Launch-blocking); unenforced dataset/evidence permissions → Pilot-fix, Launch-blocking if business-unit access is sold; synchronous report generation → Pilot-fix.

---

## 9. What this means for Phase 1

Not a plan — that is Phase 1's deliverable — but the constraints the research imposes on it:

- **Fix before polish.** Items 7, 2 and 4 in the risk register are cheap and must land before any design work is shown, or the first review will be of a product that crashes on its central flow.
- **The design system has to be built for tables first.** Every weak screen is weak because of the table component; cards and charts are secondary.
- **A pilot needs a catalogue-authoring surface.** Without metric, formula, source, entity and period editors a customer cannot leave the demo tenant, regardless of how the dashboards look.
- **Scoped users need a scoped default**, not a 403: the entity selector must be constrained by `entity_ids` and the default entity must be the user's own.
- **Backend work is unavoidable for a deployable artefact**: production config validation, tenant bootstrap, a job runner for recalculation and report generation, storage keys relative to a tenant-partitioned root, and one PostgreSQL run in CI.
- **Keep the AI pipeline as it is.** Nothing in the research suggests weakening guardrails, evaluation or governance for the sake of the UI; the copilot's provenance display is the strongest thing the product does today and the new design should make it more prominent, not less.
