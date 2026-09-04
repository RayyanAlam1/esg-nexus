# Guide: Add a framework

Frameworks are YAML configuration in `frameworks/`; no code change is needed. The loader (`backend/app/engines/frameworks.py::load_from_yaml`) upserts the framework, its version and its requirements; the coverage engine, report templates, agents and the knowledge base pick the new framework up automatically.

Related: [../FRAMEWORKS.md](../FRAMEWORKS.md) · [add-report-section.md](add-report-section.md).

---

## 1. Create the file

`frameworks/tcfd.yaml`:

```yaml
# TCFD — Recommendations of the Task Force on Climate-related Financial Disclosures (2017), 11 recommended disclosures.
framework:
  code: TCFD                         # registry code; prefix "TCFD" must match the requirement codes below (see §4)
  name: TCFD Recommendations
  publisher: Task Force on Climate-related Financial Disclosures
  description: Four pillars (governance, strategy, risk management, metrics and targets) with eleven recommended disclosures.
  jurisdiction: Global
version:
  version: "2017"
  effective_date: 2017-06-29
  status: current
  source_url: https://www.fsb-tcfd.org/recommendations/
requirements:
  - code: TCFD.GOV.A
    title: Board oversight of climate-related risks and opportunities
    pillar: governance
    theme: Governance
    disclosure_type: narrative
    metrics: [GOV.BOARD.SUSTAINABILITY_OVERSIGHT]
  - code: TCFD.STRAT.C
    title: Resilience of the strategy under different climate scenarios, including a 2°C or lower scenario
    pillar: environment
    theme: Strategy
    disclosure_type: narrative
    metrics: [ENV.CLIMATE.SCENARIO_ANALYSIS]
    guidance: "The 2023 report describes a preliminary TCFD assessment only — narrative gap."
  - code: TCFD.MT.B
    title: Scope 1, Scope 2 and, if appropriate, Scope 3 GHG emissions and related risks
    pillar: environment
    theme: Metrics and Targets
    disclosure_type: quantitative
    metrics: [ENV.GHG.SCOPE1, ENV.GHG.SCOPE2, ENV.GHG.SCOPE3]
  - code: TCFD.MT.C
    title: Targets used to manage climate-related risks and opportunities and performance against targets
    pillar: environment
    theme: Metrics and Targets
    disclosure_type: both
    metrics: [ENV.CLIMATE.PARIS_TARGET_SET, ENV.CLIMATE.GHG_TARGET]
```

Field reference: [../FRAMEWORKS.md §1](../FRAMEWORKS.md#1-yaml-schema). Optional keys per requirement: `description`, `evidence_required` (default true), `is_core` (default true), `applicability` (JSON, informational), `parent` (code of a parent requirement; only leaf requirements count toward alignment).

## 2. Reference existing metric codes

`metrics` must list codes from the metric library (`seed/ecorp_2023/metrics_*.yaml` or `POST /metrics`). Unknown codes are stored but never resolve to a metric, so the requirement will always be `missing`. Where the organisation does not report a metric, keep the code (it documents the gap) and add a `guidance` note.

Optionally add the requirement codes to the metrics' `frameworks` lists so they appear on the metric detail page.

## 3. Load it

- Start-up: the seeder calls `load_from_yaml` for every file in `ESG_FRAMEWORKS_DIR`.
- Running instance: `POST /frameworks/reload` (capability `framework.manage`) — idempotent; returns `{"loaded": [...]}`. Requirements are upserted by code; removed requirements are not deleted.
- Docker: the image copies `frameworks/` to `/frameworks`; rebuild the image or mount the directory.

Verify:

```bash
curl localhost:8000/api/v1/frameworks -H "authorization: Bearer $T"                    # requirement_count
curl "localhost:8000/api/v1/frameworks/TCFD/coverage?period=FY2023" -H "authorization: Bearer $T"
```

## 4. Make it selectable for reports

`ReportBuilder._applicable_sections` keeps a section when one of its `requirements` has a prefix (text before the first dot) equal to the framework code's prefix (text before the first underscore). `TCFD.*` ↔ `TCFD` therefore works; a framework coded `MY_STD` needs requirement codes `MY.*`. `SDG.*` is special-cased to `UN_SDG`.

Add sections that reference the new requirement codes to a template (see [add-report-section.md](add-report-section.md)), then create reports with `"framework_codes": ["WEF_SCM", "TCFD"]`.

## 5. Select it for the organisation and period

```bash
curl -X POST localhost:8000/api/v1/frameworks/select -H "authorization: Bearer $T" -H 'content-type: application/json' \
  -d '{"framework_codes": ["TCFD"], "period_code": "FY2023"}'
```

This records `organization_frameworks` rows (`GET /frameworks/selected`). Readiness and the Evaluation Centre use the frameworks passed to them (`frameworks=` query parameter, report `framework_codes`, default `WEF_SCM,UNGC,UN_SDG`).

## 6. Record omissions and tenant mappings

```bash
curl -X POST localhost:8000/api/v1/frameworks/mappings -H "authorization: Bearer $T" -H 'content-type: application/json' \
  -d '{"requirement_code": "TCFD.STRAT.C", "mapping_type": "omitted", "omission_reason": "Scenario analysis not yet performed; planned for FY2025."}'
```

An `omitted` mapping removes the requirement from the applicable set; `direct`/`partial`/`derived`/`narrative` mappings add a metric to the requirement's metric list.

## 7. Knowledge base and agents

On the next reseed the framework becomes `KB-FW-TCFD` (one chunk per requirement) so agents can cite `[TCFD.MT.B]`. To let the Standards Mapping Agent detect the framework from free text, add a keyword pair to `StandardsMappingAgent._framework_in` in `backend/app/ai/agents/specialists.py` (e.g. `("tcfd", "TCFD")`) — the only code change involved, and optional.

## 8. Tests

Add assertions to the framework tests (`GET /frameworks` count, coverage statuses for a requirement with and without data) as described in [../TESTING.md](../TESTING.md#34-api-tests-teststest_api_py).
