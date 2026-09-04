# Guide: Add a governance rule

Governance rules are rows in `governance_rules` evaluated by `backend/app/engines/rules.py`. A rule has a scope (which context it sees), a condition (safe expression), a severity and an action. Rules can be added in the seed file or at runtime.

Related: [../GOVERNANCE.md](../GOVERNANCE.md) (schema, DSL, context fields, actions, seeded rules) · [../TESTING.md](../TESTING.md#33-engine-tests).

---

## 1. Decide scope, condition and action

| Goal | Scope | Context fields available |
|---|---|---|
| Check a metric value (evidence, quality, estimates, status) | `metric_value` | `metric.*`, `entity.*`, `period.*`, `value`, `is_null`, `status`, `source_type`, `is_estimate`, `evidence_count`, `verified_evidence_count`, `quality_score`, `confidence`, `report_status` |
| Gate an AI output | `ai_output` | `agent`, `confidence`, `has_sources`, `unsupported_numbers`, `missing_citations`, `injection_detected`, `guardrail_passed` |
| Gate report approval / final generation | `report` | `report.status`, `readiness`, `blocking_issues`, `critical_issues`, `high_issues`, `unapproved_sections`, `framework_alignment` |
| Prevent data writes | `data_change` | `object_type`, `report_status`, `period_status`, `user_roles` |

Actions: `WARN`, `ESCALATE`, `REQUIRE_APPROVAL`, `REQUIRE_EVIDENCE`, `REQUIRE_HUMAN_REVIEW` (issue only) — `BLOCK`, `BLOCK_REPORT_GENERATION`, `PREVENT_DATA_MODIFICATION` (blocking). CRITICAL severity also makes an issue block the report.

## 2. Write the condition in the safe DSL

Allowed: comparisons, `and/or/not`, `in`, arithmetic, `is None`, attribute access, and the whitelisted functions (`abs, round, min, max, sum, len, safe_div, pct, yoy, coalesce, nz, sqrt, float, int, str, lower, startswith, contains`). Test it before saving:

```bash
curl -X POST localhost:8000/api/v1/governance/rules/test -H "authorization: Bearer $T" -H 'content-type: application/json' -d '{
  "condition": "metric.pillar == '"'"'environment'"'"' and metric.is_kpi and is_estimate and quality_score is not None and quality_score < 80",
  "context": {"metric": {"pillar": "environment", "is_kpi": true}, "is_estimate": true, "quality_score": 72}}'
# → {"result": true}
```

Unsafe syntax returns `{"error": "Disallowed syntax: …"}`.

## 3a. Add it to the seed (versioned)

`seed/ecorp_2023/governance.yaml`, under `rules:`:

```yaml
  - code: GR-007
    description: Estimated environmental KPIs with a quality score below 80 require verified evidence before approval
    severity: HIGH
    scope: metric_value
    condition: "metric.pillar == 'environment' and metric.is_kpi and is_estimate and quality_score is not None and quality_score < 80 and verified_evidence_count == 0"
    action: REQUIRE_EVIDENCE
    message: "Estimated KPI {metric.code} for {entity.code} ({period.code}) scores {quality_score} and has no verified evidence."
    required_action: Replace the estimate with measured data or link and verify supporting evidence.
    owner: ESG Manager
    policy: POL-ESG-DATA
```

`message` placeholders use the flattened context (`{metric.code}`, `{quality_score}`, `{agent}`, `{critical_issues}` …). The seeder sets `approval_status: approved`, `is_active: true` and `effective_date` (default 2024-01-01). Reload with `POST /admin/reseed` or a fresh start.

## 3b. Add it at runtime (capability `governance.manage`)

```bash
curl -X POST localhost:8000/api/v1/governance/rules -H "authorization: Bearer $T" -H 'content-type: application/json' -d '{
  "code": "GR-007",
  "description": "Estimated environmental KPIs with a quality score below 80 require verified evidence before approval",
  "severity": "HIGH", "scope": "metric_value",
  "condition": "metric.pillar == '"'"'environment'"'"' and metric.is_kpi and is_estimate and quality_score is not None and quality_score < 80 and verified_evidence_count == 0",
  "action": "REQUIRE_EVIDENCE",
  "message": "Estimated KPI {metric.code} for {entity.code} ({period.code}) scores {quality_score} and has no verified evidence.",
  "required_action": "Replace the estimate with measured data or link and verify supporting evidence.",
  "owner": "ESG Manager", "version": "1.0", "approval_status": "approved", "policy_code": "POL-ESG-DATA"}'
```

Rules created with `approval_status: draft` are stored inactive; activate with `PUT /governance/rules/GR-007` `{"approval_status": "approved", "is_active": true}`. Every create/update is audited (`rule.create`, `rule.update`).

## 4. Run and observe

```bash
curl -X POST "localhost:8000/api/v1/governance/rules/run?period=FY2023" -H "authorization: Bearer $T"      # metric_value scope
curl "localhost:8000/api/v1/governance/issues?severity=HIGH" -H "authorization: Bearer $T"
```

`metric_value` rules also run automatically on value writes, status changes, evidence links, recalculation and the worker job; `ai_output` rules on every agent run; `report` rules during report validation; `data_change` rules before writes. Issues carry `rule_code`, `required_action` and `blocks_report`, and change readiness through the severity penalty (HIGH −1.5 each).

## 5. Adding a new action (code change)

1. Append the name to `RULE_ACTIONS` in `backend/app/models/governance.py`.
2. If it must block, add it to `BLOCKING_ACTIONS` in `backend/app/engines/rules.py`.
3. Map it to an issue category in `CATEGORY_BY_ACTION` (`backend/app/services/governance_service.py`).
4. Implement the effect where relevant (e.g. `BaseAgent.run` for AI outputs, `check_data_change` for writes, `ReportBuilder.validate` for reports).

## 6. Tests

Add a trigger/non-trigger pair using the engine directly:

```python
from app.engines.rules import evaluate_rules
from app.models.governance import GovernanceRule

def test_gr007_triggers_only_for_unverified_estimates():
    rule = GovernanceRule(code="GR-007", severity="HIGH", scope="metric_value", action="REQUIRE_EVIDENCE",
                          condition="metric.pillar == 'environment' and metric.is_kpi and is_estimate and quality_score is not None and quality_score < 80 and verified_evidence_count == 0")
    ctx = {"metric": {"pillar": "environment", "is_kpi": True}, "is_estimate": True, "quality_score": 72, "verified_evidence_count": 0}
    assert evaluate_rules([rule], ctx)[0].triggered
    ctx["verified_evidence_count"] = 1
    assert not evaluate_rules([rule], ctx)[0].triggered
```

## 7. Checklist

- [ ] Condition handles `None` explicitly (`quality_score is not None and …`).
- [ ] Severity and action are consistent (CRITICAL/blocking only for conditions that must stop publication).
- [ ] `message` and `required_action` tell the user what to do; `owner` names the accountable role.
- [ ] Linked to a policy (`policy_code`) where one exists.
- [ ] Documented in the seeded rules table of [../GOVERNANCE.md](../GOVERNANCE.md#4-seeded-rules-seedecorp_2023governanceyaml).
