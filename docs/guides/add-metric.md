# Guide: Add a metric

Metrics are data. A new metric needs a definition (catalogue entry), optionally a formula, values with evidence, framework links and — for KPIs — validation rules. Two routes exist: the seed YAML (versioned, reproducible, loaded at start-up) and the API (`POST /metrics`, runtime).

Related: [../DATA_MODEL_ESG.md](../DATA_MODEL_ESG.md) · [../GOVERNANCE.md](../GOVERNANCE.md#2-condition-dsl-enginessafe_exprpy) · [../TESTING.md](../TESTING.md#32-golden-calculation-tests-teststest_golden_calculationspy).

---

## Route A — seed YAML (recommended for catalogue changes)

### 1. Choose the topic

Topics live in `seed/ecorp_2023/topics.yaml`. Use an existing `code` (e.g. `ghg_emissions`, subtopic `scope3`) or add one:

```yaml
  - {code: supply_chain, pillar: social, name: Supply Chain, subtopics: [screening, audits]}
```

### 2. Add the definition

Append to the pillar file, e.g. `seed/ecorp_2023/metrics_social.yaml`. Raw metric with entity values:

```yaml
  - code: SOC.SUPPLY.SUPPLIERS_SCREENED
    name: Suppliers screened on ESG criteria
    topic: supply_chain
    subtopic: screening
    unit: count
    data_type: integer
    kind: raw
    aggregation: sum
    direction: higher_is_better
    is_kpi: true
    frameworks: [GRI.308-1]              # requirement codes that exist in frameworks/*.yaml
    materiality: ethics_compliance       # optional code from materiality.yaml
    validation: {min: 0, max_yoy_change_pct: 100}
    evidence_required: true
    assurance: not_assured
    description: Number of tier-1 suppliers screened using ESG criteria during the period.
    method: Count from the supplier due-diligence register.
    values:
      EFERT: {FY2023: 120}
      EPCL:  {FY2023: 85}
    evidence: [P36]                      # printed report pages → EV-RPT23-P36
    notes: "Only EFERT and EPCL operate supplier screening; the group total is consolidated by the engine."
```

Derived metric (formula in the placeholder DSL; see [../DATA_MODEL_ESG.md §4](../DATA_MODEL_ESG.md#4-formula-dsl)):

```yaml
  - code: SOC.SUPPLY.SCREENED_PCT
    name: Share of suppliers screened
    topic: supply_chain
    subtopic: screening
    unit: "%"
    data_type: percentage
    kind: percentage
    aggregation: none                    # ratios are never summed across entities
    direction: higher_is_better
    formula: "pct({SOC.SUPPLY.SUPPLIERS_SCREENED}, {SOC.SUPPLY.SUPPLIERS_TOTAL})"
    inputs: [SOC.SUPPLY.SUPPLIERS_SCREENED, SOC.SUPPLY.SUPPLIERS_TOTAL]
    evidence_required: false
    description: Screened ÷ total tier-1 suppliers × 100; Data unavailable when the total is not disclosed.
```

If the report also prints the derived number, store it as a reported value with a tolerance so the engine checks it instead of overwriting it:

```yaml
    validation: {tolerance_pct: 5}
    source_type: reported
    values: {ECORP: {FY2023: 58}}
    evidence: [P36]
```

Narrative metric:

```yaml
  - code: SOC.SUPPLY.DUE_DILIGENCE_APPROACH
    name: Supplier due-diligence approach
    topic: supply_chain
    subtopic: screening
    data_type: text
    kind: narrative
    aggregation: none
    text_values: {ECORP: {FY2023: "Suppliers sign the Supplier Code of Conduct; high-risk suppliers are audited annually."}}
    evidence: [P36]
```

Gap (no values): omit `values`; the metric shows `Data unavailable`, rule GR-003 raises a MEDIUM issue if it is a KPI at group level, and requirements mapped to it become `missing`/`partial`.

### 3. Map it to frameworks (optional)

Add the metric code to the `metrics` list of the relevant requirement in `frameworks/<framework>.yaml` (this drives coverage) and list the requirement code in the metric's `frameworks` key (this drives the reverse index on the metric page).

### 4. Link a target (optional)

`seed/ecorp_2023/targets.yaml`:

```yaml
  - metric: SOC.SUPPLY.SCREENED_PCT
    entity: ECORP
    baseline_value: 58
    target_value: 100
    direction: increase
    kind: absolute
    target_year: 2026
    status: active
    description: Screen all tier-1 suppliers by 2026.
    evidence: P36
```

### 5. Reload

The seeder is idempotent: restart the API with `ESG_AUTO_SEED=true` and an unseeded database, or call `POST /admin/reseed` as `admin@esgnexus.local`. Recalculation, quality scoring and rule evaluation run automatically for FY2022 and FY2023.

### 6. Add a golden test

Add a row to the golden table and a test in `backend/tests/test_golden_calculations.py` (see [../TESTING.md](../TESTING.md#32-golden-calculation-tests-teststest_golden_calculationspy)):

```python
def test_supplier_screened_pct(client, db):
    t, m, e, p = _ctx(db, "SOC.SUPPLY.SCREENED_PCT")
    res = metric_engine.calculate(db, t.id, m, e, p, persist=False)
    assert res.status == "ok" and res.value == pytest.approx(205 / 353 * 100, rel=1e-6)
```

---

## Route B — API (runtime)

```bash
# 1. definition (capability metric.write)
curl -X POST localhost:8000/api/v1/metrics -H "authorization: Bearer $T" -H 'content-type: application/json' -d '{
  "code": "SOC.SUPPLY.SUPPLIERS_SCREENED", "name": "Suppliers screened on ESG criteria",
  "pillar": "social", "topic_code": "supply_chain", "subtopic_code": "screening",
  "unit": "count", "data_type": "integer", "kind": "raw", "aggregation": "sum",
  "direction": "higher_is_better", "is_kpi": true, "evidence_required": true,
  "applicable_frameworks": ["GRI.308-1"], "validation_rules": {"min": 0}}'

# 2. value with evidence (capability data.write; runs guardrail, governance, recalculation, quality, rules)
curl -X POST localhost:8000/api/v1/metrics/SOC.SUPPLY.SUPPLIERS_SCREENED/values -H "authorization: Bearer $T" \
  -H 'content-type: application/json' -d '{"entity_code": "EFERT", "period_code": "FY2023", "value_numeric": 120,
  "evidence_codes": ["EV-RPT23-P36"], "reason": "Supplier register extract"}'

# 3. approve a formula version for a derived metric (capability metric.approve)
curl -X POST localhost:8000/api/v1/metrics/SOC.SUPPLY.SCREENED_PCT/formula -H "authorization: Bearer $T" \
  -H 'content-type: application/json' -d '{"formula": "pct({SOC.SUPPLY.SUPPLIERS_SCREENED}, {SOC.SUPPLY.SUPPLIERS_TOTAL})", "version": "1.1", "description": "…"}'

# 4. promote the value
curl -X POST localhost:8000/api/v1/metrics/SOC.SUPPLY.SUPPLIERS_SCREENED/status -H "authorization: Bearer $T" \
  -H 'content-type: application/json' -d '{"entity_code": "EFERT", "period_code": "FY2023", "status": "validated"}'
```

`POST /metrics` accepts the `MetricIn` fields (`code, name, pillar, topic_code, subtopic_code, unit, data_type, kind, formula, description, calculation_method, evidence_required, applicable_frameworks, materiality_topic, validation_rules, aggregation, direction, is_kpi, assurance_status`); `pillar` must be given explicitly through the API.

---

## Checklist

- [ ] Code follows `PILLAR.TOPIC.NAME` (ENV/SOC/GOV/ECO) so agents recognise it.
- [ ] `aggregation: none` for ratios, percentages, intensities, YoY and checks.
- [ ] `validation` has `min`/`max` where physically meaningful and `max_yoy_change_pct` for KPIs.
- [ ] Every value has at least one `evidence` reference when `evidence_required` is true (otherwise GR-002 raises an issue for KPIs).
- [ ] No value is invented: leave gaps empty and explain them in `description`/`notes`.
- [ ] Framework requirement codes exist; run `POST /frameworks/reload` after editing `frameworks/*.yaml`.
- [ ] Knowledge base: the metric definition becomes a chunk in `KB-METRIC-DEFINITIONS` on the next reseed.
