# Governance

Governance in ESG Nexus is *code and data*: rules are rows evaluated by a deterministic engine, their outcomes become issues that feed report readiness, blocking actions raise hard errors, human decisions are recorded as approvals, and every change is written to an append-only audit trail.

Related: [ARCHITECTURE.md](ARCHITECTURE.md#4-deterministic-engines-appengines) · [API.md](API.md#212-governance--governance-audit) · [SECURITY.md](SECURITY.md) · [guides/add-governance-rule.md](guides/add-governance-rule.md).

---

## 1. Rule schema (`models/governance.py::GovernanceRule`)

| Field | Type | Meaning |
|---|---|---|
| `code` | string, unique per tenant | Identifier (`GR-001`) |
| `description` | text | Human description |
| `severity` | `INFO, LOW, MEDIUM, HIGH, CRITICAL` | Drives readiness penalties and issue ordering |
| `scope` | `metric_value, ai_output, report, data_change, requirement` | Which context the condition is evaluated against |
| `condition` | text | Safe expression over the scope context (§2) |
| `action` | `BLOCK, WARN, ESCALATE, REQUIRE_APPROVAL, REQUIRE_EVIDENCE, REQUIRE_HUMAN_REVIEW, PREVENT_DATA_MODIFICATION, BLOCK_REPORT_GENERATION` | Effect when triggered (§3) |
| `message` | text | Template rendered with `{path.to.field}` placeholders from the context |
| `required_action` | text | Instruction shown on the issue |
| `owner` | string | Accountable role/person |
| `version`, `effective_date` | | Rule versioning |
| `approval_status` | `draft, approved, retired` | Only `approved` **and** `is_active` rules run |
| `is_active` | bool | Set from `approval_status == "approved"` on creation |
| `params` | JSON | Reserved for parameterised rules |
| `policy_code` | string | Link to a `governance_policies` row |

Seeded rules come from `seed/ecorp_2023/governance.yaml` (keys `policy` → `policy_code`, `effective_date` defaults to 2024-01-01, `approval_status` forced to `approved`). Rules can also be created and updated through `POST/PUT /governance/rules` (capability `governance.manage`) and tested with `POST /governance/rules/test`.

---

## 2. Condition DSL (`engines/safe_expr.py`)

Conditions (and metric formulas) are Python expressions restricted by an AST whitelist and evaluated with no builtins.

### Allowed syntax

- Literals, names, attribute access (`metric.code`), subscripts (`ctx["value"]`), tuples and lists
- Arithmetic `+ - * / // % **`, unary `- + not`
- Comparisons `== != < <= > >= in not in is is not`
- Boolean `and or`, conditional expressions `a if cond else b`
- Calls to whitelisted functions only

Disallowed: imports, lambdas, comprehensions, assignments, dunder names/attributes, any function outside the whitelist. Violations raise `ExpressionError("Disallowed syntax: …")` at parse time; `POST /governance/rules` rejects such conditions.

### Whitelisted functions (`SAFE_FUNCTIONS`)

| Function | Behaviour |
|---|---|
| `abs, round, min, max, len, sqrt, float, int, str` | Standard; `min`/`max` ignore `None` |
| `sum(*args)` | Sums scalars and lists, ignores `None`; returns `None` when nothing remains |
| `safe_div(a, b, default=None)` | `None` (or default) when `a` is `None` or `b` is `None`/0 |
| `pct(a, b, default=None)` | `safe_div × 100` |
| `yoy(current, previous, default=None)` | `(current − previous) / |previous| × 100` |
| `coalesce(*args)` | First non-`None` |
| `nz(v, default=0)` | `default` when `v` is `None` |
| `lower(s), startswith(s, p), contains(s, p)` | String helpers, `None`-safe |

Division by zero evaluates to `None` (not an error). `None` comparisons follow Python semantics (`quality_score is not None and quality_score < 70`).

### Context fields per scope

| Scope | Fields | Built by |
|---|---|---|
| `metric_value` | `metric.{code, name, pillar, topic, kind, evidence_required, is_kpi, assurance_status, materiality_topic}`, `entity.{code, kind, in_boundary}`, `period.{code, status}`, `value`, `is_null`, `status`, `reporting_status`, `source_type`, `is_estimate`, `evidence_count`, `verified_evidence_count`, `quality_score`, `confidence`, `report_status` | `engines/rules.py::metric_value_context` — evidence counts include value-level links and metric-level links whose evidence has no period or the same period |
| `ai_output` | `agent`, `confidence`, `has_sources`, `unsupported_numbers` (count), `missing_citations`, `injection_detected`, `guardrail_passed` | `ai/agents/base.py::BaseAgent.run` |
| `report` | `report.{status, id}`, `readiness` (overall %), `blocking_issues` (open issues with `blocks_report` and severity ≠ CRITICAL), `critical_issues`, `high_issues`, `unapproved_sections`, `framework_alignment` | `services/governance_service.py::report_context` |
| `data_change` | `object_type`, `report_status` (status of an approved/published report for the period, else `None`), `period_status`, `user_roles` | `governance_service.check_data_change` |
| `requirement` | Reserved (no context builder yet) | — |

Message templates use the flattened context: `{metric.code}`, `{entity.code}`, `{period.code}`, `{quality_score}`, `{agent}`, `{critical_issues}` …

---

## 3. Actions

| Action | Blocking | Effect |
|---|---|---|
| `WARN` | no | Issue only |
| `ESCALATE` | no | Issue (category governance); Governance Agent lists `ESCALATE …` lines for CRITICAL issues |
| `REQUIRE_APPROVAL` | no | Issue (category approval); AI outputs → `requires_review` |
| `REQUIRE_EVIDENCE` | no | Issue (category evidence_gap) |
| `REQUIRE_HUMAN_REVIEW` | no | Issue (category data_quality); AI outputs → `requires_review` |
| `BLOCK` | yes | AI outputs → `blocked`; metric values → issue with `blocks_report` |
| `BLOCK_REPORT_GENERATION` | yes | Report validation check 7 fails (CRITICAL) → report `blocked`; final generation / approval raise `governance_blocked` |
| `PREVENT_DATA_MODIFICATION` | yes | `check_data_change` raises `GovernanceBlockedError` (HTTP 422) before any write |

`BLOCKING_ACTIONS = {BLOCK, BLOCK_REPORT_GENERATION, PREVENT_DATA_MODIFICATION}`. An issue has `blocks_report = action ∈ BLOCKING_ACTIONS or severity == CRITICAL`. Issue category by action: `CATEGORY_BY_ACTION` in `governance_service.py` (WARN → data_missing, REQUIRE_EVIDENCE → evidence_gap, REQUIRE_HUMAN_REVIEW → data_quality, REQUIRE_APPROVAL → approval, others → governance).

---

## 4. Seeded rules (`seed/ecorp_2023/governance.yaml`)

Fifteen rules are shipped; codes are non-contiguous within GR-001…GR-024.

| Code | Scope | Severity | Condition | Action | Owner / policy |
|---|---|---|---|---|---|
| GR-001 | metric_value | CRITICAL | `metric.code == 'ENV.GHG.SCOPE1' and status in ('final', 'approved') and evidence_count == 0` | BLOCK_REPORT_GENERATION | ESG Manager / POL-ESG-DATA |
| GR-002 | metric_value | HIGH | `metric.evidence_required and metric.is_kpi and not is_null and evidence_count == 0` | REQUIRE_EVIDENCE | ESG Manager / POL-ESG-DATA |
| GR-003 | metric_value | MEDIUM | `metric.is_kpi and entity.kind == 'group' and is_null and metric.kind != 'narrative'` | WARN | ESG Analyst |
| GR-004 | metric_value | MEDIUM | `metric.is_kpi and quality_score is not None and quality_score < 70` | REQUIRE_HUMAN_REVIEW | ESG Analyst |
| GR-005 | metric_value | LOW | `is_estimate and metric.assurance_status == 'limited' and not is_null` | REQUIRE_APPROVAL | Reviewer |
| GR-006 | metric_value | LOW | `metric.is_kpi and status == 'final' and evidence_count > 0 and verified_evidence_count == 0` | WARN | Auditor |
| GR-010 | ai_output | HIGH | `confidence is not None and confidence < 0.75` | REQUIRE_HUMAN_REVIEW | Reviewer / POL-AI-USE |
| GR-011 | ai_output | CRITICAL | `unsupported_numbers > 0` | BLOCK | ESG Manager / POL-AI-USE |
| GR-012 | ai_output | MEDIUM | `not has_sources` | REQUIRE_HUMAN_REVIEW | Reviewer / POL-AI-USE |
| GR-013 | ai_output | HIGH | `injection_detected` | BLOCK | Org Admin |
| GR-020 | data_change | HIGH | `report_status in ('approved', 'published')` | PREVENT_DATA_MODIFICATION | Org Admin / POL-ESG-DATA |
| GR-021 | report | CRITICAL | `critical_issues > 0 or blocking_issues > 0` | BLOCK_REPORT_GENERATION | Report Approver |
| GR-022 | report | HIGH | `unapproved_sections > 0` | BLOCK_REPORT_GENERATION | Report Approver |
| GR-023 | report | MEDIUM | `framework_alignment is not None and framework_alignment < 60` | WARN | ESG Manager |
| GR-024 | report | MEDIUM | `readiness is not None and readiness < 80` | REQUIRE_APPROVAL | Report Approver |

Policies seeded alongside: `POL-COC` (Code of Conduct), `POL-HSE`, `POL-TAX`, `POL-SPEAKOUT` (whistleblower), `POL-ESG-DATA` (platform data governance) and `POL-AI-USE` (platform AI assistance policy).

---

## 5. When rules run

| Trigger | Function | Scope |
|---|---|---|
| Seed / reseed, `POST /governance/rules/run`, `POST /calculations/recalculate`, value upsert, value status change, evidence link, worker job | `run_metric_rules(db, tenant, org, period)` | metric_value — every value in the period plus every KPI at group level without a value (raises "missing" issues); stale `evidence_gap`/`data_missing` issues auto-resolved |
| Every agent run | `check_ai_output(db, tenant, ctx)` | ai_output |
| Manual value write, ingestion load | `check_data_change(...)` | data_change (raises on blocking outcome) |
| Report validation, approval, final generation | `check_report(db, tenant, report)` | report |

Issues are upserted by fingerprint (`sha1(rule|metric|entity|period|requirement)`), so repeated runs update rather than duplicate them; codes are sequential `ISS-00001`.

---

## 6. Issues and criticality

| Field | Values |
|---|---|
| `severity` | INFO, LOW, MEDIUM, HIGH, CRITICAL |
| `category` | evidence_gap, data_missing, data_quality, inconsistency, framework_gap, governance, ai_quality, approval, target |
| `status` | `open` → `acknowledged` (`metric.validate`) → `resolved` (`metric.approve`) or `exception_approved` (`governance.exception`, reason mandatory; sets `blocks_report=false` and records an `approvals` row) |
| `blocks_report` | true for blocking actions or CRITICAL severity |

Readiness treats `open` and `acknowledged` issues as open. `GET /governance/issues` orders by severity and returns `open_by_severity` counts. Evidence gaps are also computed live by `GET /evidence/gaps`.

---

## 7. Approvals and workflow states

`approvals` rows represent human-in-the-loop decisions for `metric_value, report_section, report, ai_output, exception, mapping` objects: `POST /governance/approvals` (capability `review`) creates a request in state `requires_review`; `POST /governance/approvals/{id}/decide` records `approved | rejected | changes_requested` (approving a `report` or `exception` additionally requires a role allowed to enter the `approved` state). Pending approvals reduce the readiness `human_approvals` component by 5 points each when no report is in scope.

Report and section workflow (`security.WORKFLOW_TRANSITIONS`):

```
draft → ai_generated → validating → requires_review → reviewed → approved → published
                                          ↘ rejected                      (blocked: set by validation)
```

- Analysts/managers move sections to `ai_generated`/`requires_review`; reviewers to `reviewed`/`rejected`; report approvers to `approved`/`published`.
- Editing `content_md` through `PUT /reports/{id}/sections/{code}` marks the section `narrative_source="human"` and increments its version.
- `POST /reports/{id}/transition` to `approved`/`published` re-runs the nine checks and requires every section approved; both states set `locked=true`; `published` stamps `published_at` and marks all sections published.
- Once a report for a period is approved or published, GR-020 prevents any metric value modification for that period.

Metric value workflow: `draft → validated (metric.validate) → approved / final (metric.approve)`.

---

## 8. Report readiness (`engines/readiness.py`)

```
readiness = 0.18 × data_completeness      # KPIs with a value in the period (any entity) / KPIs
          + 0.17 × data_quality           # mean QualityScore.overall in the period
          + 0.17 × evidence_coverage      # evidence-required values with ≥ 1 evidence link / such values
          + 0.16 × framework_alignment    # mean alignment_pct across selected frameworks (0 if none)
          + 0.12 × governance_checks      # 100 − Σ penalty(open issues): INFO 0, LOW 0.2, MEDIUM 0.6, HIGH 1.5, CRITICAL 4.0 (floor 0)
          + 0.08 × ai_evaluation          # mean Evaluation.overall (dimension ai); 100 when nothing evaluated yet
          + 0.12 × human_approvals        # with a report: approved sections / sections; otherwise 100 − 5 × pending approvals
ready_to_publish = (no open issue with blocks_report) and readiness ≥ 80
```

Every component is explained in `Readiness.explanation`; `blocking_issues` lists the issues that prevent publication with their required actions. Exposed by `GET /evaluations/readiness`, `GET /esg/overview`, the `get_report_readiness` tool and stored on `reports.readiness`.

---

## 9. Nine pre-generation checks (`reports/builder.py::validate`)

| # | Check | Passes when | Severity on failure |
|---|---|---|---|
| 1 | `data_validation` | every non-narrative section metric has a value (a handful of missing values are tolerated: the threshold expression allows at most 3) | MEDIUM |
| 2 | `metric_validation` | `recalculate_all` produces no `error` runs | HIGH |
| 3 | `framework_validation` | alignment ≥ 50 % for every selected framework | MEDIUM |
| 4 | `evidence_validation` | every valued, evidence-required section metric has evidence | HIGH |
| 5 | `narrative_validation` | every `ai`/`data` section has content | HIGH |
| 6 | `numerical_consistency` | no AI narrative contains a number outside the governed values (current and prior period) of its metrics | CRITICAL |
| 7 | `governance_validation` | no `report`-scope rule with a blocking action is triggered (`check_report`) | CRITICAL |
| 8 | `ai_evaluation` | no evaluated section scores below 70 | MEDIUM |
| 9 | `report_completeness` | every section is approved/published | HIGH |

`blocked = any CRITICAL failure`; the result (`checks`, `readiness`, `governance` outcomes, `reason`, `required_action`) is stored on `reports.validation_result` and the report status becomes `blocked`, `requires_review` (unapproved sections) or `reviewed`.

---

## 10. Audit trail

`core/audit.py::record(db, tenant_id, user_id, action, object_type, object_id, old_value, new_value, reason, ip)` appends to `audit_logs`; there is no update or delete path in the codebase. Actions written by the platform include:

`auth.login`, `entity.create`, `period.create`, `metric.create`, `data.modify`, `metric_value.<status>`, `calculation.run`, `calculation.version`, `calculation.recalculate_all`, `target.create`, `data_source.create`, `data.upload`, `evidence.upload`, `evidence.link`, `evidence.verify`, `framework.select`, `framework.reload`, `framework.map`, `materiality.update`, `policy.create`, `rule.create`, `rule.update`, `rules.run`, `issue.acknowledge`, `issue.resolve`, `issue.exception`, `approval.request`, `approval.<decision>`, `ai.generate`, `ai.copilot`, `report.create`, `report.generate_draft`, `report.validate`, `report_section.<state>`, `report.<state>`, `report.generate_draft_file`, `report.generate_final`, `user.create`, `user.roles`, `admin.reseed`.

`GET /audit` (capability `audit.read`) supports filtering by action prefix, object type/id, user, free text and date range; the metric detail page shows the last 20 entries whose `object_id` starts with the metric code.
