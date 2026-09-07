# Phase 1 — Build plan

Date: 2026-09-07 · Input: [PHASE_0_FINDINGS.md](PHASE_0_FINDINGS.md) · Status: proposal, awaiting owner approval before any implementation code is written

Sections:

1. [Principles that shape the plan](#1-principles-that-shape-the-plan)
2. [Design system](#2-design-system)
3. [Information architecture](#3-information-architecture)
4. [Build sequence and milestones](#4-build-sequence-and-milestones)
5. [Backend changes and where they sit](#5-backend-changes-and-where-they-sit)
6. [Definition of done and how it is verified](#6-definition-of-done-and-how-it-is-verified)
7. [Working agreement](#7-working-agreement)
8. [Decisions needed from the owner](#8-decisions-needed-from-the-owner)

---

## 1. Principles that shape the plan

1. **Fix before polish.** The preview-page crash, the cross-tenant leaks, the path-traversal write and the unusable builder ship in the first milestone, before a single token is changed. Nobody reviews a redesign of a product that crashes on its central flow.
2. **One vertical slice before breadth.** After the foundation, the second milestone takes one real metric from CSV upload to a published PDF through the new UI. Everything after that widens the same patterns.
3. **Tables first.** Every weak screen in Phase 0 is weak because of the table component. The data grid is the first serious component built, and every list screen migrates to it.
4. **The credibility pipeline is untouchable.** Deterministic engines compute; agents explain and draft; guardrails → evaluation → governance → human review stays exactly as it is. The UI makes provenance more visible, never less.
5. **Every screen is backed by a real endpoint.** New screens are only planned where an endpoint exists or is listed in §5 as a backend deliverable in the same milestone.
6. **Alignment, not compliance.** The word "compliance" leaves the navigation and the copy; the backend never computed it.
7. **Incremental, reviewable work.** Each milestone ends with something you can open in a browser, a list of what changed, and what is still open.

---

## 2. Design system

The system is implemented as CSS custom properties (the source of truth), mapped into Tailwind's theme so existing utility classes keep working while every colour, size and shadow resolves to a token. Light and dark themes are two sets of the same functional tokens; components never reference a raw colour.

### 2.1 Colour

**Neutral scale.** Twelve steps generated in OKLCH at fixed lightness intervals with a slight cool hue (hue 250, chroma ≤ 0.012 so the greys stay neutral next to chart colours). Anchors are chosen so that the Stripe rule holds: any text token is ≥ 5 steps from any background token it is allowed on (≥ 4.5:1), any icon/border-emphasis token ≥ 4 steps (≥ 3:1). Contrast is verified by a script in the repo, not by eye.

| Role token | Light | Dark | Use |
|---|---|---|---|
| `bg-canvas` | N0 `#ffffff` | N12 `#0b0e14` | page ground |
| `bg-surface` | N0 `#ffffff` | N11 `#111620` | cards, tables, panels |
| `bg-muted` | N1 `#f6f7f9` | N10 `#171d28` | table headers, sidebars, inset areas |
| `bg-inset` | N2 `#eef0f3` | N12 `#0b0e14` | code blocks, wells |
| `bg-overlay` | N0 + overlay shadow | N9 `#1e2532` | menus, dialogs (dark lifts the surface) |
| `border-default` | N4 `#d0d5dd` | N8 `#2f3846` | structural borders |
| `border-muted` | N3 `#e3e6ea` | N9 `#1e2532` | row dividers |
| `border-emphasis` | N6 `#8b95a5` | N6 `#6b7688` | focused/hovered borders |
| `fg-default` | N11 `#1a1f29` | N1 `#f2f4f7` | body text |
| `fg-muted` | N8 `#5b6573` | N4 `#9aa4b2` | secondary text, labels |
| `fg-subtle` | N7 `#7a8494` | N6 `#6b7688` | placeholders, disabled |
| `fg-on-emphasis` | N0 | N0 | text on filled buttons/badges |

The exact hex values above are the OKLCH targets rounded; the generator script is the authority and will be committed with the tokens so the scale can be regenerated when the accent changes.

**Accent.** One brand hue, teal, kept from the current identity and retuned: `accent-fg` (text/links, 4.5:1 on both canvases), `accent-emphasis` (primary buttons, the only saturated fill on a page), `accent-muted` (selected rows, active nav), `accent-subtle` (hover wash). Light: `#0f766e / #0d9488 / #ccfbf1 / #f0fdfa`; dark: `#5eead4 / #14b8a6 / #134e4a / #0f2f2c`.

**Semantic roles.** Each role has `fg`, `muted` (background + border for chips) and `emphasis` (filled). Light values shown; dark values are regenerated at equal lightness.

| Role | fg | muted bg | emphasis | Used for |
|---|---|---|---|---|
| success | `#1a7f37` | `#dafbe1` | `#1f883d` | passed checks, verified evidence, achieved targets |
| attention | `#9a6700` | `#fff8c5` | `#bf8700` | warnings, MEDIUM severity, unverified |
| danger | `#cf222e` | `#ffebe9` | `#cf222e` | blocked, CRITICAL/HIGH severity, rejected |
| info | `#0969da` | `#ddf4ff` | `#0969da` | LOW/INFO severity, informational |
| ai | `#6639ba` | `#fbefff` | `#8250df` | anything produced by an agent (drafts, analysis, routing) so AI output is always visually distinct from governed data |

**State roles** (the vocabulary of this product; mapped onto the semantic roles so the palette stays small):

| Family | States | Rendering |
|---|---|---|
| Report / section workflow | draft, ai_generated, validating, requires_review, reviewed, approved, published, rejected, blocked | neutral → ai → attention → info → success → success-emphasis → danger |
| Metric value status | draft, validated, approved, locked, unavailable | neutral / info / success / success + lock icon / dashed neutral |
| Value provenance | reported, calculated, consolidated, estimated | icon + label (document, sigma, tree, tilde) — never colour alone |
| Evidence | verified, unverified, rejected | success / attention / danger |
| Issue severity | CRITICAL, HIGH, MEDIUM, LOW, INFO | danger-emphasis, danger, attention, info, neutral |
| Target | achieved, active, missed, not_set | success / info / danger / dashed attention |

**Chart palette.** Pillar colours (environment, social, governance, prosperity) plus six categorical hues, all generated at equal OKLCH lightness per theme; sequential and diverging ramps derived from the accent and the danger/success pair. Colour is never the only encoding: series get labels or direct annotations.

### 2.2 Typography

Font: Inter variable, self-hosted and subset (Latin), with `-apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif` fallback; mono `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace`. `font-variant-numeric: tabular-nums lining-nums` is applied globally to numeric cells, KPI values, timestamps, hashes and codes.

| Token | Size / line | Weight | Letter-spacing | Use |
|---|---|---|---|---|
| `display` | 28 / 32 | 600 | −0.02 em | KPI hero values, report title |
| `title-lg` | 24 / 32 | 600 | −0.015 em | page titles on landing screens |
| `title` | 20 / 28 | 600 | −0.01 em | page titles |
| `heading` | 16 / 24 | 600 | 0 | card and section headings |
| `subheading` | 14 / 20 | 600 | 0 | table section labels, dialog titles |
| `body` | 14 / 20 | 400 | 0 | default |
| `body-strong` | 14 / 20 | 500 | 0 | emphasised body, row titles |
| `small` | 13 / 20 | 400 | 0 | default table density, secondary rows |
| `caption` | 12 / 16 | 400 | 0 | captions, helper text, table headers (500, uppercase off) |
| `metric` | 24 / 28 | 600 | −0.01 em | KPI tile values |
| `code` | 12.5 / 20 | 400 mono | 0 | codes, formulas, hashes |

Rules: no weight below 400 anywhere; uppercase tracking labels are retired (the current `label` class) in favour of caption-size sentence case in `fg-muted`; headings never exceed 28 px inside the app.

### 2.3 Spacing, sizing, radius, layout

- Spacing scale: 2, 4, 6, 8, 12, 16, 20, 24, 32, 40, 48, 64 (4-px grid, 8-px rhythm).
- Control heights: 28 (toolbar/dense), 32 (default), 40 (form primary). Icon sizes 14/16/20.
- Radii: 4 (inputs, badges, chips), 6 (buttons, cards, table containers), 12 (dialogs, popovers, drawers), 9999 (counters only). 0 inside grids.
- Layout: sidebar 240 px expanded / 56 px collapsed; content gutter 16 → 24 at ≥ 1280 px; narrative pages max 1120 px; data pages full-bleed. Breakpoints 768 / 1012 / 1280 / 1440. Tablet (≥ 768) is supported; phone is explicitly out of scope for v1 (decision 8.5).

### 2.4 Elevation

Three levels only:

| Level | Light | Dark | Where |
|---|---|---|---|
| flat | 1 px `border-default`, no shadow | same | cards, tables, panels, tiles |
| raised | `0 1px 1px rgb(0 0 0 / .04), 0 1px 3px rgb(0 0 0 / .06)` | surface lifted one step + same shadow at .3/.4 | sticky table headers when stuck, hover-lifted interactive cards, the context bar |
| overlay | `0 0 0 1px border-default, 0 6px 12px -3px rgb(0 0 0 / .12), 0 6px 18px rgb(0 0 0 / .08)` | `bg-overlay` surface + ring + `0 8px 24px rgb(0 0 0 / .5)` | menus, popovers, dialogs, drawers, toasts |

### 2.5 Motion

| Tier | Duration | Easing | Applies to |
|---|---|---|---|
| micro | 100 ms | ease | hover/focus colour, icon rotation, checkbox |
| state | 180 ms | enter `cubic-bezier(.3,.8,.6,1)`, exit `cubic-bezier(.7,.1,.75,.9)` | expand/collapse, tab indicator, row selection, chip add/remove |
| surface | 260 ms | move `cubic-bezier(.2,0,0,1)` | drawer, dialog, popover, copilot panel, sidebar collapse |
| page | 150 ms | ease-out | route content fade-in (no slide) |

Never animated: numbers, table sort/filter results, chart data updates, audit rows, status badges, readiness scores, skeleton-to-content swaps for data that was already on screen. `prefers-reduced-motion` sets every duration to 0. No library: CSS transitions plus Radix presence for mount/unmount.

### 2.6 Component inventory

Primitives (built on Radix UI for keyboard and screen-reader behaviour; styled with the tokens):

| Component | States / variants | Notes |
|---|---|---|
| Button | primary, secondary, ghost, danger, ai; sizes 28/32/40; loading, disabled, icon-only | the only saturated element on a page is the primary action |
| Input, Textarea, Select, Combobox, DatePicker, NumberInput | default, focus ring (2 px accent), invalid, disabled, read-only, with prefix/suffix | NumberInput uses tabular figures and unit suffix |
| Checkbox, Radio, Switch, SegmentedControl | | |
| Badge / StatusBadge / SeverityBadge / ProvenanceBadge | per state family in §2.1 | label + icon, never colour-only |
| Chip (filter chip, evidence chip, metric-code chip) | removable, clickable | replaces the current `[Q 100]` glyph clusters with labelled chips |
| Tooltip, Popover, DropdownMenu, ContextMenu | | |
| Dialog, Drawer (right, 480/720 px), ConfirmDialog | | all destructive and workflow actions confirm with a reason field where the backend records one |
| Tabs (underline, pill) | count badges | |
| Card, Tile (KPI), Stat | flat / raised / interactive | |
| Toast / Inline alert | success, attention, danger, info | |
| Skeleton, EmptyState, ErrorState, NotAuthorised | | ErrorState shows the error envelope's code and request id |
| PageHeader | title, description, context (period · entity), primary action, secondary actions, breadcrumbs | |
| ContextBar | period, entity (scoped to the user's `entity_ids`), theme, density, copilot | replaces the current top-right selects |
| CommandPalette (Ctrl-K) | navigate, jump to metric/evidence/report by code | uses existing search endpoints |
| Sidebar | collapsible groups, collapsed icon rail, keyboard navigable, role-filtered | |
| DataTable v2 | TanStack Table: column sizing by type, sticky header + first column, three densities (28/36/44), sort with `aria-sort`, server pagination "21–40 of 142", column visibility, row selection, expandable rows, toolbar with filter chips, empty/error/loading states, CSV export of the current view | the core of the product |
| DescriptionList | | metadata panels |
| Timeline | | audit history, report version history |
| Charts (Recharts, themed) | line (trend with real period axis), bar (comparison), stacked bar, donut/ring (readiness, quality), scatter (materiality), sparkline | tokens supply colours; tooltips use the overlay style; no animation on data |
| ProvenancePanel | value → formula → inputs → dataset → source → evidence | reused on metric detail, report section, copilot answer |
| AIOutputFrame | the "ai" role frame around any agent output with confidence, guardrail, evaluation and governance outcome | makes the pipeline visible everywhere agents speak |
| Markdown renderer | themed typography for narratives | |

A `/design` route (admin only, dev builds) renders every component in every state in both themes; it doubles as the visual regression surface.

---

## 3. Information architecture

### 3.1 Navigation

Nine top-level sections, each collapsible, filtered by capability. Landing page depends on role (executive → Overview; contributor → My data; reviewer/approver → Review queue; auditor → Evidence).

| Section | Screens | Capability |
|---|---|---|
| **Overview** | Home (role-specific), Readiness | read |
| **Performance** (was ESG Intelligence) | ESG overview, Environment, Social, Governance, Prosperity, Entity comparison | read |
| **Data** | Sources, Datasets & versions, Upload, Data quality, Lineage | read; write actions by `data.write` |
| **Metrics** | Library, Metric detail, Metric editor (definition, formula versions, runs), KPIs, Calculations, Targets | `metric.write` for editors |
| **Standards** | Frameworks, Requirements, Mappings, Alignment (was Compliance), Materiality assessment, Materiality matrix | `framework.manage` for selection/mapping |
| **Evidence** | Repository, Evidence detail, Upload, Gaps & verification queue | `evidence.write` / `evidence.verify` |
| **Governance** | Issues, Approvals (queue + request), Policies (list + editor), Rules (list + editor + test), Audit trail | `governance.manage`, `audit.read` |
| **Reports** | Reports, Report builder, Report workspace (preview, sections, review, versions, files) | `report.build`, `review`, `report.approve` |
| **AI** | Copilot (also as a global panel), Agents & tools, Runs, Evaluation, Knowledge base, Search | `ai.run` for copilot/agents |
| **Administration** | Organisation structure (entities, periods), Users & roles, Tenant settings, System | `admin`; tenant settings `tenant.admin` |

Global: context bar (period, entity), command palette, notifications, copilot panel, user menu (profile, password, theme, density, sign out).

### 3.2 Capability → screen map

Every backend capability, including the 24 endpoints with no UI today, mapped to a screen, with the milestone that delivers it. P0 = needed for the vertical slice, P1 = needed for a pilot, P2 = completeness.

| Backend capability (router) | Screen | Priority | Milestone |
|---|---|---|---|
| auth: login, me, refresh | Login; silent refresh in the client; profile in user menu | P0 | M1 |
| organizations: read; create entity/period | Administration → Organisation structure (tree editor, period editor) | P1 | M3 |
| esg: overview, pillar, topics, entity comparison | Home, Performance section | P1 | M5 |
| metrics: list, detail, values, create definition, status workflow, calculate, formula versions, runs, lineage | Library, Metric detail (value workflow moved into a "Value" panel with status, approve/reject with reason), Metric editor with formula version diff and run history | P0 detail; P1 editor | M2 / M3 |
| targets | Targets list + editor drawer | P1 | M3 |
| calculations, quality, lineage | Calculations, Data quality, Lineage (graph + table view) | P1 | M3 |
| datasets: sources, upload, versions, records, load, classify, create source | Data section incl. Source editor; upload wizard with column classification preview | P0 upload; P1 editors | M2 / M3 |
| evidence: list, detail, create, **file upload**, link, verify, gaps, kinds | Evidence repository with drag-drop upload, detail with viewer for PDF pages, verification queue | P0 link; P1 upload | M2 / M4 |
| frameworks: registry, select, reload, requirements, requirement detail, coverage, mappings, gap analysis | Standards section; requirement detail drawer; reload restricted to tenant admin | P1 | M4 |
| materiality: assessments, topics, **stakeholders**, analyze | Assessment with stakeholder input panel | P1 | M4 |
| governance: policies (list, **create**), rules (CRUD, test, run), issues (list, acknowledge, resolve, exception), approvals (list, **request**, decide) | Governance section; approval request from any object's action menu | P0 issues; P1 rest | M2 / M4 |
| audit | Audit trail with object filter; per-object timelines | P1 | M4 |
| agents: list, **tools**, run, runs, run detail | Agents & tools (tool registry visible), Runs | P1 | M5 |
| copilot: ask, experts, suggestions | Global copilot panel + full page | P0 panel | M1 / M5 |
| knowledge: documents, search | Knowledge base, Search | P2 | M5 |
| evaluations: list, summary, **readiness**, trend | Evaluation with readiness tile | P2 | M5 |
| reports: templates, CRUD, draft, validate, preview, **preview.html**, sections, regenerate, transition, generate, **versions**, download | Report workspace: left section tree, centre page preview (uses the HTML renderer for fidelity), right panel (validation, governance, versions, actions) | P0 | M2 |
| admin: users, roles, system, reseed, notifications, health | Administration; reseed hidden outside development | P1 | M6 |
| **new** tenant bootstrap, password change/reset, deactivate, logout | Administration → Tenant settings; user menu → Profile | P1 | M6 |
| **new** job status | Global job indicator in the context bar; per-object progress (draft generation, recalculation, file generation) | P0 | M2 |

### 3.3 Pilot path

The order a first customer touches things, which drives the milestone order: Home → Upload data → Metric detail (is the number right, where did it come from) → Data quality → Standards alignment → Issues and approvals → Report workspace → Published file. Materiality, AI screens and administration are reached later in a pilot and are built later.

---

## 4. Build sequence and milestones

Effort is relative: S ≤ a day of focused work, M a few days, L about a week. Each milestone is one or more pull requests; the milestone is not done until §6 checks pass.

### M0 — Stabilise (effort M)

Purpose: remove the defects that would discredit any review, without touching the design.

1. Report preview crash: normalise `validation_result` so every `detail` is a string and `reason` is `list[str]` (structured governance outcomes move to the existing `governance` list); harden `ValidationChecks`; add a root and per-route error boundary that shows the error envelope and request id.
2. Report builder: initialise the period from context once it is loaded; disable Next only with an explanatory message.
3. Scoped users: entity selector limited to `entity_ids`; default entity = the user's first scoped entity; 403 renders NotAuthorised instead of a skeleton.
4. Cross-tenant: tenant filter on the two `Issue` queries; login resolves `(tenant, email)` with the tenant taken from the request host or an explicit tenant field; regression tests with a second seeded tenant.
5. Evidence upload path traversal: storage keys generated server-side (`{tenant}/{evidence_id}/{uuid}.{ext}`), original filename stored as metadata only.
6. Production config guard: refuse to start in `production` with the default secret; `auto_seed` defaults to false outside development and test; demo accounts on the login page only in development.
7. Issue severity ordering by rank; `set_roles` preserves entity scope.

Visible result: every route renders for every role with zero console errors; the report flow works end to end in the old UI.

### M1 — Foundation: tokens, primitives, shell (effort L)

1. Token package: OKLCH generator script, `tokens.css` (light/dark), Tailwind theme mapping, contrast check script wired into CI.
2. Inter variable self-hosted; typography and numeric rules.
3. Primitives from §2.6 (Radix-based), DataTable v2, charts theme, AIOutputFrame, ProvenancePanel.
4. AppShell v2: collapsible role-filtered sidebar, context bar with scoped entity/period, command palette, notifications, copilot panel, theme and density preferences (persisted per user in local storage; server-side preference is a P2).
5. `/design` gallery route; Playwright visual snapshots of the gallery in both themes.
6. Login page redesigned (no demo credentials outside development).

Visible result: the shell, login, and a gallery of every component in both themes; existing pages render inside the new shell unchanged (they still use old components until their milestone).

### M2 — Vertical slice: one metric from upload to published PDF (effort L)

Walks `ENV.WASTE.TOTAL` for EFERT through the whole product in the new UI:

1. Data → Upload wizard (file, mapping preview via the classify endpoint, defaults, validation results, load) and Dataset version detail with records table.
2. Metric detail redesigned: value panel (status, provenance, approve/reject with reason), trend with a real period axis, tabs → sections (calculation, inputs, evidence, mapping, quality, governance, audit, lineage) using the new components; "Analyse with copilot" inside AIOutputFrame.
3. Evidence link flow from the metric (pick existing evidence, or upload).
4. Governance → Issues with acknowledge/resolve/exception (reason required) and Approvals queue.
5. Report builder rebuilt on the wizard pattern; Report workspace (section tree, HTML page preview, validation panel, section review with edit-in-drawer, transitions with reason, versions and downloads).
6. Backend: job runner for draft generation, validation, final generation and full recalculation with a job status endpoint and UI progress (see §5); `(report_id, version)` uniqueness; transitions respect `locked` and state order.

Visible result: a scripted demo you can follow yourself: upload a CSV with one changed value → see the issue it raises → link evidence → resolve → draft → review → approve → publish → download the PDF, as the manager, reviewer and approver.

### M3 — Data and metrics breadth (effort L)

Library (DataTable v2 with column sizing by type, saved filters), Metric editor (definition CRUD, formula versions with diff and dry-run calculate, run history), Targets editor, Calculations, Data quality (table fixed, explanation as expandable row), Lineage graph + table view, Sources editor, Organisation structure editor (entities tree, periods). Backend: none new beyond §5 items scheduled here.

### M4 — Standards, evidence, governance breadth (effort L)

Frameworks and requirement detail drawer, Mappings editor, Alignment page (renamed), Materiality assessment with stakeholder inputs and matrix, Evidence repository with file upload and PDF page viewer, verification queue, Gaps, Policies list and editor, Rules list/editor/test, Audit trail with timelines.

### M5 — Home, performance and AI (effort M)

Role-specific Home, Readiness, Performance section with re-themed charts and batched data loading (target: dashboard < 1.5 s on SQLite, no request waterfalls), Entity comparison, Agents & tools, Runs, Evaluation with readiness tile, Knowledge base and Search, full-page Copilot.

### M6 — Platform hardening for deployment (effort L)

Tenant bootstrap and settings, user lifecycle (password change/reset, deactivate, logout with refresh-token rotation and revocation), storage adapter with tenant-partitioned relative keys (local and S3/MinIO), worker reliability (acknowledged jobs, retries, dead letter, restart policy, per-tenant isolation), PostgreSQL job in CI with migration and test run, generic exception handler and error tracking hook, proxy-aware rate limiting with a stricter login bucket, seeding and migration made single-runner (advisory lock), Administration screens.

### M7 — Quality pass (effort M)

Accessibility audit (axe on every route, keyboard walkthrough), dark-mode review of every screen, tablet layout, empty/error/loading state review, copy review for the alignment-not-compliance rule, documentation updates (README, API, TESTING, ONBOARDING corrected per Phase 0 §6), CHANGELOG and version tag. Hands off to Phase 3 (runbook).

Sequencing rationale: M0 first because nothing else is reviewable without it; M1 before M2 because the slice must be built on the final components or it will be built twice; M2 before M3–M5 so the patterns (table, drawer editors, workflow actions with reasons, AI frames, job progress) are proven on a real flow before being repeated across thirty screens; M6 after the UI milestones because its work is invisible in a browser but unavoidable for a deployable artefact, and its scope depends on decisions 8.3 and 8.4.

---

## 5. Backend changes and where they sit

| Change | Why | Milestone |
|---|---|---|
| Normalised `validation_result` types; error envelope for unhandled exceptions with request id | preview crash; 500s escaping the envelope | M0 |
| Tenant filters on `Issue` queries; tenant-aware login; second-tenant test fixture and isolation tests | cross-tenant leak | M0 |
| Server-generated storage keys for evidence uploads | path traversal | M0 |
| Production config validation; `auto_seed` default per environment | default secret and seeded admin | M0 |
| Issue severity rank ordering; `set_roles` keeps entity scope; entity-scoped default in `get_entity` | correctness | M0 |
| Job runner: `jobs` table (id, tenant, type, status, progress, result, error, requested_by), `POST` endpoints return `202 {job_id}` for draft, validate, generate, recalculate, reseed; `GET /jobs/{id}`; worker executes with acknowledgement; synchronous fallback in development when no Redis | synchronous multi-minute requests; recalculation on every write | M2 (runner + report jobs), M3 (recalculation) |
| Recalculation scoped to affected metrics (dependency closure) instead of `recalculate_all` on every value write | performance | M3 |
| Report transitions enforce `locked` and the state graph; `report_versions` unique `(report_id, version)` | governance freeze bypass; version race | M2 |
| Entity scoping in `IngestionPipeline.load` and list endpoints (values, targets, quality, evidence, records, reports, audit) | scoped users | M2 (load), M3–M4 (lists) |
| Batched read endpoints for Home and pillar pages | request waterfalls | M5 |
| Tenant bootstrap (`POST /tenants` for super-admin + CLI), user lifecycle (change/reset password, deactivate, logout, refresh rotation + revocation list) | onboarding a real customer | M6 |
| Storage adapter (`local`, `s3`), tenant-partitioned relative keys, migration of existing absolute keys | multi-replica, tenant isolation of files | M6 |
| Worker: acknowledged queue, retry with backoff, dead-letter list, per-tenant sessions, restart policy in Compose | job loss, crash on error | M6 |
| PostgreSQL service in CI; `String` length fixes; `LIKE` → `ILIKE`/`func.upper`; advisory lock around migrations and seeding | PostgreSQL never exercised; deploy races | M6 |
| Proxy-aware rate limiting (`X-Forwarded-For` behind a trusted proxy setting), login bucket, bucket pruning | auth hardening | M6 |
| `POST /frameworks/reload` restricted to `tenant.admin`; reseed only in development | global registry mutation | M0 |
| Docs corrections listed in Phase 0 §6 | honesty | M7 |

Explicitly scoped out (with reason): vector search remains BM25 (retrieval quality is not a pilot blocker and the adapter exists); OIDC/SAML (needs a customer identity provider to test against; JWT with rotation is sufficient for a pilot); dataset/evidence-level `permissions` JSON (entity scoping covers the pilot need; document-level ACLs are a v2 feature); phone layouts.

---

## 6. Definition of done and how it is verified

You will not be asked to trust screenshots. Each milestone ships with the following, and the milestone summary links to the artefacts.

**Automated, in CI on every PR**

1. Backend: `ruff`, `pytest` on SQLite **and** PostgreSQL (from M6), including the new tenant-isolation and entity-scoping tests; coverage cannot drop below the previous milestone.
2. Frontend: typecheck, build, unit tests for the token contrast script and the table column-sizing logic.
3. **Role crawl** (the Phase 0 Playwright crawl, promoted into the repo): every route × every role must render with zero console errors, zero uncaught exceptions, zero unexpected 4xx/5xx, and a non-empty main region or an explicit NotAuthorised/Empty state. This is the check that would have caught all three Phase 0 defects.
4. **Flow tests**: upload → issue → evidence → resolve → draft → review → approve → publish → download, run as the manager, reviewer and approver; copilot question returns an answer with sources; scoped contributor sees only their entity.
5. **Accessibility**: axe on every route, zero serious/critical violations; keyboard-only completion of the flow tests.
6. **Visual snapshots** of the `/design` gallery and every page in light and dark; diffs reviewed on the PR.
7. **Performance budget**: Home and pillar pages < 1.5 s to content on SQLite in CI; no page issues more than 6 requests on load.

**Reviewed by you at each milestone**

- A short milestone note: what changed, how to run it, what is open, what trade-offs were made.
- A demo script you can follow in under ten minutes with the seeded accounts.
- Light and dark screenshots of every changed screen committed under `docs/phase2/<milestone>/`.

**Phase 2 is done when** M0–M7 have merged, the checks above are green on `main`, a v1.1.0 tag has produced images, and the vertical slice can be performed by you on a clean `docker compose up` against PostgreSQL without touching the API directly.

---

## 7. Working agreement

- One pull request per milestone step (M0 will be two or three; M2 several), each green in CI, each authored by you. You are the reviewer; branch protection on `main` requires a review, so merges happen when you approve, or you can tell me to merge directly with your admin bypass as was done for the initial publish.
- No milestone starts before the previous one's summary is posted, so problems surface early.
- Anything that turns out harder than planned is flagged with a revised proposal in the milestone note, not silently cut.
- Commit messages follow Conventional Commits; the CHANGELOG is updated per milestone.

---

## 8. Decisions needed from the owner

1. **Default theme.** Proposal: light by default, dark available, both first-class. (GitHub and most enterprise sustainability teams work in light; auditors print.)
2. **Rename "Compliance" to "Alignment" and "ESG Intelligence" to "Performance".** Proposal: yes, to keep the language discipline consistent in the navigation.
3. **Is business-unit (entity-scoped) access a sold feature for the pilot?** If yes, the list-endpoint scoping in M3–M4 is mandatory; if no, it can slide to M6.
4. **Storage target for the pilot.** Proposal: S3-compatible object storage via the adapter (MinIO in Compose, S3 in cloud) with local filesystem retained for development.
5. **Phone layouts out of scope for v1** (tablet in). Proposal: yes.
6. **Merge mechanics.** PRs approved by you, or direct pushes to `main` by me as you did for the initial publish? Proposal: PRs, so you see every change; merging with admin bypass is fine when you prefer speed.
7. **Dependabot backlog.** Proposal: I merge the minor bumps in M0 after CI is green and leave the Python 3.14 base image and Recharts 3 majors for M5/M6 where they are tested.

Reply with the decision numbers you want changed; anything you do not mention proceeds as proposed. No implementation code is written until you approve this plan.
