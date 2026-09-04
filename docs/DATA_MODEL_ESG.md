# ESG Data Model

This document describes the ESG ontology implemented by the models, engines and seed data, and the YAML formats used to load a reference dataset.

Related: [DATABASE.md](DATABASE.md) · [FRAMEWORKS.md](FRAMEWORKS.md) · [GOVERNANCE.md](GOVERNANCE.md) · [guides/add-metric.md](guides/add-metric.md).

---

## 1. Ontology

```
Tenant
└── Organization (ECORP)
    ├── ReportingPeriod (FY2021, FY2022 [baseline], FY2023, FY2024)
    ├── Entity tree (group → subsidiary | joint_venture | associate → business_unit | plant | office | foundation | trading)
    │     consolidation_method, ownership_pct, in_reporting_boundary, attributes (water_stressed, certifications, …)
    ├── EsgTopic (pillar: environment | social | governance | prosperity) → EsgSubtopic
    │     └── MetricDefinition (code, kind, unit, formula, validation, frameworks, materiality, assurance)
    │           ├── MetricValue (entity × period): numeric or text, status, source_type, confidence, quality_score
    │           │     ├── CalculationRun (formula version, inputs, result)           ← lineage anchor
    │           │     ├── DatasetVersion → Dataset → DataSource                        ← origin
    │           │     └── EvidenceLink → Evidence (report page, policy, statement…)  ← proof
    │           ├── CalculationVersion (versioned, approved formula)
    │           ├── Target (baseline, target, direction, status incl. not_set)
    │           ├── FrameworkMapping → Requirement → FrameworkVersion → Framework
    │           └── QualityScore (7 dimensions)
    ├── MaterialityAssessment → MaterialityTopic (impact × financial scores) + StakeholderInput
    ├── GovernancePolicy / GovernanceRule → Issue → Approval
    └── Report (template, frameworks, readiness) → ReportSection (metrics, requirements, evidence, narrative) → ReportVersion (file)
```

Every reported number resolves along the chain `Report Section → Metric Value → Calculation Run (formula, version) → Input Values → Dataset Version → Data Source → Evidence`, which `engines/lineage.py` materialises as a graph.

---

## 2. Metric definition fields

`metric_definitions` (`models/esg.py::MetricDefinition`); the *seed key* column gives the YAML key read by `seed/loader.py::_metrics`.

| Column | Seed key | Values / meaning |
|---|---|---|
| `code` | `code` | `PILLAR.TOPIC.NAME` convention: `ENV.GHG.SCOPE1`, `SOC.OHS.TRIR_EMP`, `GOV.BOARD.WOMEN_PCT`, `ECO.EVGD.WEALTH_GENERATED` (prefixes ENV/SOC/GOV/ECO are recognised by agents' `CODE_RE`) |
| `name`, `description` | `name`, `description` | |
| `pillar` | derived from topic | environment, social, governance, prosperity |
| `topic_code`, `subtopic_code` | `topic`, `subtopic` | Must exist in `topics.yaml` |
| `unit` | `unit` | Free text (`tCO2e`, `GJ`, `ML`, `t`, `%`, `headcount`, `PKR mn`, `per 200,000 h`) |
| `frequency` | `frequency` | default `annual` |
| `data_type` | `data_type` | `decimal, integer, percentage, ratio, boolean, text, currency, count` — drives validity checks and the input guardrail |
| `kind` | `kind` | `raw` (stored), `derived`, `ratio`, `intensity`, `percentage`, `yoy` (all formula-driven), `aggregate`, `narrative` (text values), `target` |
| `calculation_method` | `method` | Human-readable methodology |
| `formula` | `formula` | Expression in the placeholder DSL (§4); presence creates `CalculationVersion 1.0` |
| `required_inputs` | `inputs` | Metric codes the formula depends on (documentation; the engine parses placeholders) |
| `data_sources` | `sources` | Source codes (informational) |
| `evidence_required` | `evidence_required` (file `defaults` apply) | Drives traceability scoring, evidence gaps, GR-002 |
| `evidence_requirements` | `evidence_requirements` | Text describing acceptable evidence |
| `applicable_frameworks` | `frameworks` | Requirement codes (`WEF.PLANET.GHG_EMISSIONS`, `GRI.305-1`, …) |
| `materiality_topic` | `materiality` | Code in `materiality.yaml` |
| `assurance_status` | `assurance` (file `defaults`) | `not_assured, limited, reasonable` |
| `validation_rules` | `validation` | `{min, max, allowed, max_yoy_change_pct, tolerance_pct}` — `tolerance_pct` bounds reported-vs-recalculated differences |
| `aggregation` | `aggregation` | `sum` (default), `weighted_avg`, `avg`, `last`, `none`, `max` — consolidation across children |
| `direction` | `direction` | `lower_is_better, higher_is_better, neutral` — trend classification on KPI cards |
| `tags`, `owner` | `tags`, `owner` | |
| `is_kpi` | `is_kpi` | KPI cards, readiness completeness, GR-002/003/004/006 |
| `is_active`, `version` | — | `version` increments when a new formula version is approved |

Value-level seed keys: `values: {ENTITY: {PERIOD: number}}`, `text_values: {ENTITY: {PERIOD: "text"}}`, `evidence: [P80, P81]` (printed pages → `EV-RPT23-P80`), `status` (default from file `defaults`, usually `final`), `source_type` (default `reported`), `is_estimate` (confidence 0.75 instead of 0.95), `notes` (stored on every value; used to document inconsistencies and chart-read values).

---

## 3. Seed metric YAML format

Files: `seed/ecorp_2023/metrics_environment.yaml`, `metrics_social.yaml`, `metrics_governance.yaml`, `metrics_prosperity.yaml`. Each has `defaults` and a `metrics` list.

```yaml
defaults:
  evidence_required: true
  assurance: limited          # WEF core metrics are covered by ISAE 3000 limited assurance (report p.02)
  status: final
metrics:
  # raw metric with entity-level values (consolidated to the group by the engine)
  - code: ENV.GHG.SCOPE1
    name: Scope 1 GHG emissions
    topic: ghg_emissions
    subtopic: scope1
    unit: tCO2e
    data_type: decimal
    kind: raw
    aggregation: sum
    direction: lower_is_better
    is_kpi: true
    frameworks: [WEF.PLANET.GHG_EMISSIONS, GRI.305-1, IFRS.S2.29a, ESRS.E1-6, SASB.RT-CH-110a.1, SDG.13]
    materiality: energy_emissions
    validation: {min: 0, max_yoy_change_pct: 50}
    description: Direct emissions from stationary, process and mobile combustion … plus fugitive emissions for SECMC (CH4) and EFERT (CO2).
    method: GHG Protocol Scope 1; calculations based on current data collection systems (p.81).
    values:
      EEL:   {FY2023: 5075867, FY2022: 4783758}
      EFERT: {FY2023: 1897534, FY2022: 1730120}
      EVTL:  {FY2023: 265,     FY2022: 379}
      EETL:  {FY2023: 35,      FY2022: 93}
      EPCL:  {FY2023: 324557,  FY2022: 332587}
      EEAP:  {FY2023: 2171,    FY2022: 3137}
      ENFRA: {FY2023: 26809,   FY2022: 21340}
    evidence: [P81, P82]
    notes: "ECORP (holding) Scope 1 is reported as '-' (nil); group total printed 7,327,238 (2023) / 6,871,414 (2022)."

  # derived metric whose printed value is stored as *reported* so the engine can check it
  - code: SOC.OHS.TRIR_EMP
    name: Total Recordable Incident Rate — employees (per 200,000 hours)
    topic: health_safety
    subtopic: rates
    unit: per 200,000 h
    data_type: ratio
    kind: derived
    aggregation: none
    direction: lower_is_better
    is_kpi: true
    formula: "safe_div(nz({SOC.OHS.RECORDABLE_EMP}) * 200000, {SOC.OHS.HOURS_EMP})"
    inputs: [SOC.OHS.RECORDABLE_EMP, SOC.OHS.HOURS_EMP]
    method: Recordable injuries × 200,000 ÷ hours worked (OSHA basis, as stated on p.67).
    validation: {min: 0, tolerance_pct: 10}
    source_type: reported
    values: {ECORP: {FY2023: 0.09, FY2022: 0.06}}
    evidence: [P67]
    notes: "Reported to two decimals (0.09 / 0.06); recalculated 0.0877 / 0.0552 — tolerance set to 10% to absorb rounding."

  # narrative metric (text_values instead of values)
  - code: ENV.GHG.METHODOLOGY
    name: GHG measurement approach and boundary
    topic: ghg_emissions
    subtopic: methodology
    data_type: text
    kind: narrative
    aggregation: none
    frameworks: [IFRS.S2.29a]
    text_values:
      ECORP:
        FY2023: "Sources include stationary, process and mobile combustion (excluding employee commute in company-owned vehicles); fugitive emissions included only for SECMC (CH4, mining) and EFERT (CO2, urea production). Calculations based on current data collection systems; additional data capture planned."
    evidence: [P81]

  # gap recorded honestly (no values → Data unavailable; a KPI, so GR-003 raises a MEDIUM issue at group level)
  - code: ENV.GHG.SCOPE3
    name: Scope 3 GHG emissions
    topic: ghg_emissions
    subtopic: scope3
    unit: tCO2e
    data_type: decimal
    kind: raw
    aggregation: sum
    direction: lower_is_better
    is_kpi: true
    frameworks: [WEF.PLANET.GHG_EMISSIONS, GRI.305-3, IFRS.S2.29a, ESRS.E1-6]
    materiality: energy_emissions
    description: Material upstream and downstream value-chain emissions. Not reported in 2023 — the report states effects beyond business operations are excluded due to non-availability of verifiable data (p.01). Data unavailable.
```

Loader behaviour worth knowing:

- Metrics are upserted by `(tenant, code)`; values by `(metric, entity, period)`; page evidence `EV-RPT23-P<page>` is created on first reference from `report_pages.json` (PDF page `(p + 5) // 2`, excerpt = first 1,800 characters of the page text, `verification_status` and `confidence` from `evidence.yaml::source_document`, file hash = report SHA-256).
- Reported values are attached to the pillar dataset version (`DS-RPT-ENV`, `DS-RPT-SOC`, `DS-RPT-GOV`, `DS-RPT-ECO`) so lineage shows `SRC-REPORT-2023` as the source.
- Group totals are **not** stored for raw metrics with entity values; the consolidation engine reproduces them. Printed totals kept for reconciliation use separate `*_REPORTED` metrics (e.g. `ENV.ENERGY.TOTAL_REPORTED`, `aggregation: none`).
- Derived metrics with printed values store them as `source_type: reported` with a `tolerance_pct`; the engine links a calculation run and the quality engine compares the two.

---

## 4. Formula DSL

Formulas are expressions over placeholders, evaluated by `engines/safe_expr.py` (syntax and functions in [GOVERNANCE.md](GOVERNANCE.md#2-condition-dsl-enginessafe_exprpy)).

| Placeholder | Meaning |
|---|---|
| `{CODE}` | Value of metric `CODE` for the same entity and period (consolidated from children when the entity has no own value) |
| `{CODE@prev}` | Same entity, previous period of the same granularity |
| `{CODE@entity:EFERT}` | Fixed entity, same period (e.g. `nz({SOC.WORKFORCE.NMPT@entity:EFERT})`) |

Examples from the catalogue:

```
safe_div({ENV.ENERGY.TOTAL}, {ECO.FIN.REVENUE})                                   # intensity
yoy({ENV.ENERGY.TOTAL}, {ENV.ENERGY.TOTAL@prev})                                  # YoY %
pct({SOC.WORKFORCE.HIRES}, {SOC.WORKFORCE.PERMANENT})                             # rate
nz({ENV.WASTE.HAZARDOUS}) + nz({ENV.WASTE.NON_HAZARDOUS})                         # total (treat missing as 0)
nz({ENV.WATER.WITHDRAWN}) - nz({ENV.WATER.CONSUMED}) - nz({ENV.WATER.DISCHARGED})  # balance check ≈ 0
```

A formula whose inputs are missing yields status `missing_inputs` ("Data unavailable for: …") rather than a number; use `nz()` only where a missing component legitimately means zero and say so in `description`.

---

## 5. Entity hierarchy and consolidation rules

Seeded hierarchy (`seed/ecorp_2023/organization.yaml`, report pp.07–08):

```
ECORP (group, 100 %, full)
├── ECORP-HQ (business_unit)            holding-company head office footprint
├── EFERT (subsidiary, 56.2 %, full)    → EFERT-DAHARKI (plant, water-stressed), EFERT-ZARKHEZ (plant), EFERT-AGRITRADE
├── EPCL (subsidiary, 56.19 %, full)    → EPCL-PQ (plant), THINKPVC, EPLAST, EPEROX
├── EEL (subsidiary, 100 %, full)       → EPQL (68.9 %, water-stressed), EPTL (50.1 %), SECMC (JV 11.9 %, full — management control), TF (foundation)
├── EVTL (joint_venture, 50 %, full)
├── ELENGY (subsidiary, 56 %)           → EETL (LNG terminal)
├── EVTL_EETL (business_unit)           combined reporting unit for metrics disclosed only for both terminals
├── EEAP (subsidiary, water-stressed)
├── EEFZE (trading, UAE, in_reporting_boundary: false)
├── ENFRA, ECONNECT (subsidiaries)
├── FCEPL (associate 39.93 %, equity, in_reporting_boundary: false)
└── EF (foundation)
```

Consolidation (`engines/consolidation.py`):

| Entity setting | Factor |
|---|---|
| `in_reporting_boundary = false` or `consolidation_method ∈ {equity, excluded}` | 0 (excluded; still listed in `contributions` with `included: false`) |
| `proportional` | `ownership_pct / 100` |
| `full` (default) | 1 |

Aggregation per metric: `sum` (Σ value × factor), `avg`, `weighted_avg` (weights = factors), `max`, `last`, `none` (never consolidated). Children without an own value are consolidated recursively from their children; `coverage` reports the share of children with data. The seeded entities all use `full` consolidation where in boundary (the report's boundary is "management control"), so group totals equal the sum of entity values — e.g. Scope 1 FY2023 = 7,327,238 tCO2e.

Metrics that must not be summed across entities (ratios, intensities, percentages, YoY, checks, printed totals) carry `aggregation: none`.

---

## 6. Evidence model

| Element | Description |
|---|---|
| `Evidence` | Code, title, `kind` (19 kinds: report_page, invoice, utility_bill, hr_report, safety_report, environmental_record, audit_document, certification, policy, contract, supplier_document, measurement_record, spreadsheet, pdf, image, assurance_statement, financial_statement, regulatory_filing, other), source, `document_ref`, `page_from/page_to` (PDF), `printed_page`, `excerpt`, `evidence_date`, entity/period scope, `verification_status` (unverified, verified, rejected), `confidence`, `file_hash`, `storage_key`, `meta` |
| `EvidenceLink` | Evidence → `metric_id` (applies to all values) and/or `metric_value_id` (one value), optionally `requirement_id`, `report_section_id`; `relation` supports/contradicts/context |
| Page evidence | `EV-RPT23-P<printed page>` generated from `report_pages.json`; `verification_status: verified`, `confidence: 0.9` (numbers inside the ISAE 3000 limited-assured report are treated as verified reported values); chart-read values carry lower confidence via metric `notes`/`is_estimate` |
| Non-page evidence (`evidence.yaml::items`) | `EV-ISAE3000-2023` (assurance statement, image-only pages, unverified, 0.6), `EV-POL-COC`, `EV-POL-HSE`, `EV-POL-TAX`, `EV-POL-SPEAKOUT` (policies, unverified), `EV-AR-2023` (annual report cross-reference, "Evidence required" for R&D and government assistance), `EV-IUCN-CARBON-TMT`, `EV-WRI-AQUEDUCT` — linked to metrics by `links` |

Evidence drives: traceability scoring, `GET /evidence/gaps`, rules GR-001/002/006, readiness `evidence_coverage`, requirement `evidence_gap`, report check 4, agent citations `[EV-RPT23-P81]`.

---

## 7. Targets

`targets` rows (`seed/ecorp_2023/targets.yaml`): `metric`, `entity`, `baseline_value`, `target_value`, `direction` (decrease, increase, maintain, achieve), `kind` (absolute, relative_pct, intensity, qualitative), `target_year`, `status` (active, achieved, missed, not_set), `description`, `evidence` (printed page → `source_evidence_code`). The baseline period is FY2022.

Twelve targets are seeded; four have `status: not_set` with no `target_value` to record that the report discloses **no** quantitative target (GHG total, water withdrawn, waste total, female share) — these surface as `target_status: target_not_set` on KPI cards and as gaps in the Targets section rather than invented numbers. `GET /targets` computes `progress_pct = (current − baseline) / (target − baseline) × 100` when baseline and target exist.

---

## 8. Materiality model

`materiality_assessments` (one per organisation/period; seeded "FY2023 Materiality Assessment (WEF-aligned, ERM-scored)", approach `impact`, threshold 3.0, status approved, evidence P37–P38) with `materiality_topics`:

| Field | Meaning |
|---|---|
| `impact_severity`, `impact_likelihood` (1–5) | `impact_score = severity × likelihood / 5` |
| `financial_magnitude`, `financial_likelihood` (1–5) | `financial_score = magnitude × likelihood / 5` |
| `stakeholder_priority` (1–5) | Bubble size on the matrix |
| `is_material` | From the report's list; on update, derived as `max(impact, financial) ≥ threshold` unless explicitly supplied |
| `related_metric_codes`, `related_requirement_codes`, `risks`, `opportunities`, `rationale`, `evidence_codes` | Traceability to metrics, requirements and pages |

Fourteen topics are seeded (ten material: economic performance, ethics & compliance, employee wellbeing, OHS, DEI, community, energy & emissions, water, materials, waste; four assessed below threshold: biodiversity, climate risk, cybersecurity, human rights) together with eight `stakeholder_inputs` (group, topic, priority, channel, concern). The seed file states that the report lists material topics without scores; the numeric scores are the platform's structured representation of the report's qualitative prioritisation and are editable by the ESG Manager (`PUT /materiality/assessments/{id}/topics/{code}`).

Matrix API (`GET /materiality/assessments/{id}`): `x = financial_score`, `y = impact_score`, `size = stakeholder_priority`, axis labels and threshold; each topic includes `related_metrics` with current group values (or `data_unavailable`).

---

## 9. Topics (`seed/ecorp_2023/topics.yaml`)

30 topics across the four pillars (energy, ghg_emissions, climate, water, waste, biodiversity, environmental_management; workforce, diversity_inclusion, talent_development, compensation, labor_practices, health_safety, wellbeing, community_investment; board, ethics_compliance, risk_management, stakeholder_engagement, cybersecurity, digitalization, reporting_assurance, memberships; economic_performance, wealth_distribution, tax, investment, business_performance, innovation, credit_ratings), each with subtopics. Topics are tenant-scoped rows; administrators can add more through the models (no dedicated endpoint in this release).
