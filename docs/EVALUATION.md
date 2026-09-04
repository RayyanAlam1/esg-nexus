# Evaluation Centre

The Evaluation Centre (`GET /evaluations/summary`, blueprint §N / R8) aggregates four quality dimensions — Data Quality, AI Quality, ESG Quality and Report Quality — plus Report Readiness. Every score is produced by a deterministic function so that it is reproducible and can be tracked over time.

Related: [AGENTS.md](AGENTS.md) · [GOVERNANCE.md](GOVERNANCE.md#8-report-readiness-enginesreadinesspy) · [FRAMEWORKS.md](FRAMEWORKS.md).

---

## 1. Data Quality (`engines/data_quality.py::assess`)

Scored per (metric, entity, period) on seven dimensions, each 0–100, starting from 100 and reduced by explained deductions. Persisted in `quality_scores` and mirrored to `metric_values.quality_score`.

```
overall = 0.20·completeness + 0.20·accuracy + 0.15·consistency + 0.10·timeliness
        + 0.15·validity + 0.05·uniqueness + 0.15·traceability
```

| Dimension | Deductions | Explanation text |
|---|---|---|
| completeness | No value (no row, or numeric and text both empty) → 0, and **all other dimensions 0, overall 0** | "No value recorded for this period (Data unavailable)." |
| accuracy | `is_estimate` → −25; `confidence < 0.9` → −round((0.9 − confidence) × 100); reported value differing from recalculation beyond tolerance → −20 | "Value is flagged as an estimate (-25 accuracy)." / "Recorded confidence 0.75 (-15 accuracy)." |
| validity | value < `validation_rules.min` or > `max` → 0; non-integer for `data_type=integer` → −30; percentage outside 0–100 without an explicit `max` → −40; numeric metric stored as text only → −20 | "Value 250 above maximum 100." |
| consistency | YoY change > `validation_rules.max_yoy_change_pct` (default 50 %) against the previous period → −30; for `source_type=reported` metrics with a formula, the latest `ok` calculation run is compared: `diff% = |run.result − v| / |v| × 100`; `diff% > tolerance_pct` (default 1.0) → −40 (and −20 accuracy) | "Year-over-year change 62.3% exceeds 50% threshold — review for anomaly." / "Reported value 1949 differs from recalculated 1951 by 0.10% (tolerance 0.05%)." / "Reported value agrees with recalculation (2.5% difference)." |
| timeliness | reference date (earliest linked evidence date for reported values, else record creation date) more than 365 days after period end → −30 | "Value recorded more than 12 months after period end." |
| uniqueness | duplicate (metric, entity, period) rows → 0 (prevented by the unique constraint) | — |
| traceability | `evidence_required` and no evidence → 0; evidence linked but none verified → −40; `calculated` value without a calculation run → −30; `manual` value without a source dataset → −10 | "Evidence required but none linked (Evidence required)." / "1 verified evidence item(s) linked." |

Scores are rounded to one decimal and clipped to [0, 100]. `assess_all` evaluates every value of a period; `dataset_quality` produces completeness/validity/uniqueness percentages for an ingested dataset version.

Aggregations: `GET /quality/summary` (period averages per dimension, by pillar, 15 lowest), `GET /quality/scores` (paginated), Evaluation Centre `data_quality` (overall, completeness, accuracy, consistency averages for the period).

---

## 2. AI Quality (`ai/agents/evaluation.py::score_output`)

Scored for every agent narrative (stored in `evaluations` with `dimension="ai"`, `object_type="agent_run"`) and for Evaluation Agent requests.

```
overall = 0.25·factuality + 0.20·groundedness + 0.15·relevance + 0.15·citation_correctness + 0.25·numerical_consistency
passed  = overall ≥ 70
```

| Score | Formula |
|---|---|
| factuality | `supported / (supported + unsupported) × 100` over the numbers found in the text by the output guardrail (`check_output`); 100 when the text contains no numbers |
| numerical_consistency | identical to factuality (both derive from the guardrail's number matching) |
| hallucination_rate | `100 − factuality` (reported, not weighted) |
| groundedness | share of sentences (> 3 words) whose token set overlaps ≥ 30 % with at least one fact text (metric payloads, passages, findings); 100 for empty text |
| relevance | `|question tokens ∩ answer tokens| / |question tokens| × 100`, floored at 40 when the facts contain metrics; 100 when there is no question |
| citation_correctness | share of `[...]` citations in the text that match a known citation (metric citations, sources) exactly or by first token; with no citations: 100 if there are no facts to cite, otherwise 50 |

Findings: `unsupported_numbers` (list), `low_groundedness` (< 60 %), `citation_mismatch`. The agent's confidence is capped at `overall/100 + 0.05`.

Evaluation Centre `ai_quality`: mean of each score across all AI evaluations, `evaluated_outputs`, `hallucination_rate`. `GET /evaluations/trend` returns the last 100 evaluations in time order.

---

## 3. ESG Quality

Computed live in `GET /evaluations/summary` for the default frameworks WEF_SCM, UNGC and UN_SDG:

| Score | Formula | Source |
|---|---|---|
| framework_alignment (per framework) | `(complete + 0.5 × partial) / applicable × 100` over leaf requirements not omitted | `engines/frameworks.py::coverage` |
| disclosure_completeness | `Σ completed / Σ applicable × 100` across the three frameworks | same |
| evidence_coverage | `values with ≥ 1 evidence link / evidence-required values × 100` (period) | `engines/readiness.py` component |
| metric_coverage | number of distinct metrics with a quality score in the period | `quality_scores` |

Requirement status rules and gap flags are defined in [FRAMEWORKS.md](FRAMEWORKS.md#4-coverage-and-alignment-enginesframeworkspy).

---

## 4. Report Quality

For the latest report of the period: `checks_passed`, `checks_total` and `structural_compliance = passed / total × 100` from the stored nine-check `validation_result` (see [GOVERNANCE.md](GOVERNANCE.md#9-nine-pre-generation-checks-reportsbuilderpyvalidate)); `null` when no report exists.

---

## 5. Report Readiness (`engines/readiness.py::compute`)

```
readiness = 0.18·data_completeness + 0.17·data_quality + 0.17·evidence_coverage + 0.16·framework_alignment
          + 0.12·governance_checks + 0.08·ai_evaluation + 0.12·human_approvals
```

| Component | Formula |
|---|---|
| data_completeness | KPIs (`is_kpi`, non-narrative) with a value in the period at any entity / KPIs × 100 |
| data_quality | mean `quality_scores.overall` for the period (0 when none) |
| evidence_coverage | evidence-required values with ≥ 1 link / evidence-required values × 100 |
| framework_alignment | mean `alignment_pct` across the selected frameworks (0 when none selected) |
| governance_checks | `max(0, 100 − Σ penalty)` with penalties per open/acknowledged issue: INFO 0, LOW 0.2, MEDIUM 0.6, HIGH 1.5, CRITICAL 4.0 |
| ai_evaluation | mean `evaluations.overall` (dimension ai); **100 when nothing has been evaluated yet** |
| human_approvals | with a report: approved/published sections / sections × 100; otherwise `max(0, 100 − 5 × pending approvals)` |

`ready_to_publish = (no open issue with blocks_report) and overall ≥ 80`. The result includes `open_issues` by severity, `blocking_issues` with required actions and one explanation line per component.

---

## 6. Observability block

`GET /evaluations/summary → observability`: `model_runs` count, total `prompt_tokens` and `completion_tokens`, `avg_model_latency_ms`, `guardrail_blocks` (agent runs with status `blocked`).

---

## 7. Overall scores

`overall_scores` in the summary lists the five headline numbers side by side: `ai_quality`, `data_quality`, `evidence_coverage`, `framework_alignment`, `report_readiness`. None of them is a compliance measure; they are internal readiness indicators, and the framework coverage payload carries the disclaimer "Framework Alignment is an internal readiness indicator, not a compliance certification. Final regulatory interpretation may require qualified professionals."
