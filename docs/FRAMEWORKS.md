# Frameworks

Reporting standards are configuration: each framework is a YAML file in `frameworks/`, loaded idempotently into the registry tables (`frameworks`, `framework_versions`, `requirements`) by `engines/frameworks.py::load_from_yaml` at seed time or through `POST /frameworks/reload`. The framework engine computes, per organisation and period, which requirements are complete, partial, missing or omitted and expresses the result as **alignment**, never as compliance.

Related: [DATA_MODEL_ESG.md](DATA_MODEL_ESG.md) · [EVALUATION.md](EVALUATION.md) · [guides/add-framework.md](guides/add-framework.md).

---

## 1. YAML schema

```yaml
framework:
  code: WEF_SCM                      # unique registry code (used in API paths and report framework_codes)
  name: WEF Stakeholder Capitalism Metrics (Core)
  publisher: World Economic Forum / International Business Council
  description: 21 core metrics across Governance, Planet, People and Prosperity pillars
  jurisdiction: Global               # optional
  industry: Chemicals                # optional (SASB)
  is_custom: false                   # optional
version:
  version: "2020"                    # string; one FrameworkVersion per (framework, version)
  effective_date: 2020-09-22
  status: current                    # current | superseded | draft
  source_url: https://…
  notes: …                           # optional
requirements:
  - code: WEF.PLANET.GHG_EMISSIONS   # unique within the version; prefix must match report-template filtering (see §6)
    title: Greenhouse gas (GHG) emissions
    pillar: environment              # environment | social | governance | prosperity
    theme: Climate change
    disclosure_type: quantitative    # quantitative | narrative | both (default both)
    description: …                   # optional
    evidence_required: true          # default true
    is_core: true                    # default true
    applicability: {entities: [EFERT, EPCL]}   # optional JSON; informational in this release
    metrics: [ENV.GHG.SCOPE1, ENV.GHG.SCOPE2]   # default metric mappings (codes from the metric library)
    guidance: "…"                    # optional; shown on the requirement and in the knowledge base
    parent: WEF.PLANET               # optional; hierarchical requirements (only leaves count for alignment)
```

Loading behaviour: the framework and version are upserted by code/version; each requirement is upserted by code with `sort_order` = position in the file; parents are resolved after the child is created; requirements removed from the YAML are **not** deleted from the database.

---

## 2. Shipped frameworks

| Code | File | Name | Version | Requirements | Quantitative / Narrative / Both | Role in the reference dataset |
|---|---|---|---|---|---|---|
| `WEF_SCM` | `wef_scm.yaml` | WEF Stakeholder Capitalism Metrics (Core) | 2020 | 21 | 11 / 5 / 5 | Primary framework of the 2023 report; requirement codes `WEF.GOV.*`, `WEF.PLANET.*`, `WEF.PEOPLE.*`, `WEF.PROSPERITY.*` |
| `UNGC` | `ungc.yaml` | UN Global Compact — Ten Principles | 2000 | 10 | 0 / 4 / 6 | Primary; `UNGC.P1`…`UNGC.P10`; P3 flagged as a narrative gap (collective bargaining not disclosed) |
| `UN_SDG` | `un_sdgs.yaml` | UN Sustainable Development Goals | 2015 | 17 | 0 / 1 / 16 | Primary; `SDG.1`…`SDG.17`, `evidence_required: false` |
| `GRI` | `gri_2021.yaml` | GRI Standards | 2021 | 41 | 21 / 13 / 7 | Assessment only (not claimed by the report); universal (2-x, 3-3) and topic standards |
| `IFRS_S` | `ifrs_s1_s2.yaml` | IFRS Sustainability Disclosure Standards (S1 / S2) | 2023 | 14 | 6 / 6 / 2 | Assessment; `IFRS.S2.STRATEGY.FINANCIAL` documented as a metric gap |
| `ESRS` | `esrs.yaml` | European Sustainability Reporting Standards | 2023 | 19 | 13 / 4 / 2 | Assessment subset (ESRS 2, E1, E3, E4, E5, S1, G1) |
| `SASB_CHEM` | `sasb_chemicals.yaml` | SASB Standards — Chemicals (RT-CH) | 2023-12 | 9 | 7 / 2 / 0 | Assessment for EFERT/EPCL; `RT-CH-540a.1` process safety documented as a metric gap |

Total: 131 requirements. All requirements in the shipped files are flat (no `parent`). The seeder records `organization_frameworks` rows for FY2022 and FY2023: `status: active, is_primary: true` for WEF_SCM, UNGC and UN_SDG; `status: assessment` for the others.

---

## 3. Mapping metrics to requirements

Two sources are merged when a requirement is evaluated:

1. **Default mappings** — `requirements.metric_codes` from the YAML `metrics` list.
2. **Tenant mappings** — `framework_mappings` rows with `status="approved"` (`POST /frameworks/mappings`): `mapping_type` `direct | partial | derived | narrative | omitted`, optional `metric_id`, `rationale`, `confidence`, `omission_reason`.

A metric definition also lists its requirements in `applicable_frameworks` (seed key `frameworks`); this is the reverse index shown on the metric detail page (`framework_requirements`) and used by `GET /metrics?framework=`.

### Omissions

An approved mapping with `mapping_type="omitted"` marks the whole requirement `omitted`; it is excluded from the applicable set and its `omission_reason` is returned in coverage. The seeder records one *partial* omission: `WEF.PEOPLE.WAGE_LEVEL ↔ SOC.COMP.CEO_PAY_RATIO` ("CEO pay ratio omitted due to confidential data (WEF index, p.151). Entry-level wage ratio is reported (3x)."). Because the mapping type is `partial`, the requirement remains `partial` (the wage ratio is reported, the CEO ratio is not) and the rationale is visible on the requirement, which is the intended representation of a disclosed-with-omission item.

---

## 4. Coverage and alignment (`engines/frameworks.py`)

### Requirement status (`requirement_status`)

For each mapped metric: `has_value` = any value (numeric or text) for the period at any entity of the organisation; `has_evidence` = any evidence link on those values or on the metric. `narrative` = a report section for the period references the requirement code and has content.

| Condition | Status |
|---|---|
| approved `omitted` mapping | `omitted` |
| `disclosure_type = narrative` | `complete` if narrative exists; else `partial` if any mapped metric has a value; else `missing` |
| no mapped metrics | `complete` if narrative exists and `disclosure_type = both`; else `missing` |
| mapped metrics | `complete` if all have values; `partial` if some; `missing` if none |

Gap flags: `evidence_gap` (evidence required and a valued metric has no evidence), `metric_gap` (any mapped metric without a value, or a quantitative requirement with no mapped metrics), `narrative_gap` (`narrative`/`both` requirement without a report narrative).

### Alignment (`coverage`)

```
leaf        = requirements without children
applicable  = leaf requirements whose status ≠ omitted
alignment % = (complete + 0.5 × partial) / applicable × 100
```

The payload also reports `completed`, `partial`, `missing`, `omitted`, `evidence_gaps`, `metric_gaps`, `narrative_gaps`, every requirement's status with its metric states, and the fixed disclaimer: *"Framework Alignment is an internal readiness indicator, not a compliance certification. Final regulatory interpretation may require qualified professionals."*

Where alignment is used: `GET /frameworks/{code}/coverage`, the `get_framework_mapping` tool, readiness component `framework_alignment` (mean over the report's frameworks), report check 3 (`≥ 50 %` per framework), rule GR-023 (`< 60 %` warns), the `framework_index` data section of reports, and the Standards Mapping / Assurance agents.

---

## 5. Requirement guidance and gaps in the reference dataset

Some requirements document known gaps in the 2023 report through `guidance`:

| Requirement | Guidance |
|---|---|
| `UNGC.P3` | The 2023 report does not disclose collective-bargaining coverage — narrative gap |
| `IFRS.S2.STRATEGY.FINANCIAL` | Financial implications not yet available — metric gap (`ENV.CLIMATE.FINANCIAL_EFFECTS` has no value) |
| `SASB.RT-CH-540a.1` | Process-safety incident metrics not disclosed — metric gap |

Combined with metrics that intentionally have no value (`ENV.GHG.SCOPE3`, `ENV.CLIMATE.FINANCIAL_EFFECTS`, `SOC.COMP.CEO_PAY_RATIO`, `ENV.ENERGY.RENEWABLE_CONSUMPTION`) and `ENV.CLIMATE.PARIS_TARGET_SET = 0`, these produce the `missing`/`partial` statuses that the gap analysis, readiness and the Standards Mapping Agent report.

---

## 6. Frameworks and report templates

`ReportBuilder._applicable_sections` keeps a template section when it has no `requirements`, when its `source` is `template` or `data`, or when at least one of its requirement codes belongs to a selected framework. Membership is decided by prefix: the part of the requirement code before the first dot must equal the part of the framework code before the first underscore (`WEF.…` ↔ `WEF_SCM`, `GRI.…` ↔ `GRI`, `IFRS.…` ↔ `IFRS_S`, `ESRS.…` ↔ `ESRS`, `SASB.…` ↔ `SASB_CHEM`, `UNGC.…` ↔ `UNGC`), with `SDG.…` matched to `UN_SDG`. New frameworks must follow this convention for their sections to be selectable.

---

## 7. Knowledge base integration

Each framework version becomes a knowledge document `KB-FW-<CODE>` with one chunk per requirement (code, title, description, disclosure type, metric codes, guidance), so the RAG Research and Standards Mapping agents can cite requirements as `[GRI.305-1]`. Reload the seed (or delete the document's chunks) after changing requirement text to refresh the corpus.
