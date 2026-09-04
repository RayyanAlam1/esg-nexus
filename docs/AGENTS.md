# AI Agents

The AI layer (`backend/app/ai/`) is an orchestration layer over deterministic engines. Agents never read the database directly; they obtain facts through the controlled tool registry, hand those facts to a language-model provider (or the offline template provider) for composition, and pass the result through output guardrails, evaluation and governance rules before it is persisted.

Related: [RAG.md](RAG.md) · [EVALUATION.md](EVALUATION.md) · [GOVERNANCE.md](GOVERNANCE.md) · [guides/add-agent.md](guides/add-agent.md).

---

## 1. Pipeline (`ai/agents/base.py::BaseAgent.run`)

```
run(task, payload)
 ├─ 1. Input guardrail     guardrails.check_input(all string payload values)
 │       blocked (prompt injection, sensitive data, unsupported format) → AgentResult(status="blocked") persisted
 ├─ 2. Gather facts        self.gather(task, payload)  — deterministic; uses only self.tool(name, **kwargs)
 │       tool must be in spec.tools, every call recorded in tools_used; tool errors returned as {"error": …}
 ├─ 3. Provider            if uses_llm(): provider.complete(system=BASE_SYSTEM, messages=[user prompt + "FACTS: <json>"],
 │       json_schema=spec.output_schema, purpose=task) → ModelRun row (tokens, latency, status)
 │       provider error/refusal → OfflineProvider fallback, provider recorded as "<name>→offline"
 ├─ 4. Compose             self.compose(task, payload, facts, llm_text) → output dict (answer / narrative / structured)
 ├─ 5. Output guardrail    guardrails.check_output(narrative, allowed_numbers=every number in facts, sources,
 │       require_citations=spec.narrative, selected_frameworks=payload.frameworks)
 ├─ 6. Confidence          _confidence(facts, guard) then min(confidence, evaluation.overall/100 + 0.05)
 ├─ 7. Evaluation          evaluation.score_output(narrative, facts, question, guard) → scores, overall, findings
 ├─ 8. Governance          governance_service.check_ai_output(context) → triggered ai_output rules
 ├─ 9. Status              blocked   = output guardrail blocked OR any rule with a blocking action
 │                          requires_review = blocked OR rule action ∈ {REQUIRE_HUMAN_REVIEW, REQUIRE_APPROVAL}
 │                                            OR confidence < ESG_AI_CONFIDENCE_THRESHOLD (0.75)
 │                          status = blocked | requires_review | completed
 └─ 10. Persist            AgentRun (+ Evaluation dimension="ai", passed = overall ≥ 70) (+ ModelRun[])
```

The system prompt (`BASE_SYSTEM`) fixes five rules: use only the FACTS block; write "Data unavailable"/"Evidence required" for missing values; cite every figure with the supplied citation (e.g. `[ENV.GHG.SCOPE1 · ECORP · FY2023]`, `[KB-REPORT-2023 p.81-82]`); never claim a framework is complied with; formal corporate language. The expert hint from the MoE router and the agent's responsibilities are appended.

### Confidence

`_confidence` (base.py): 0.2 when the facts contain no metrics, sources or findings; otherwise `0.6 + 0.35 × (metrics with values / metrics)` (0.7 when there are no metrics but sources/findings exist), −0.3 for unsupported numbers, −0.1 for missing citations, clipped to [0, 0.98]. After evaluation: `min(confidence, overall/100 + 0.05)`, rounded to 2 decimals.

### Thresholds

| Threshold | Value | Where |
|---|---|---|
| Human review on low confidence | `< 0.75` (`ESG_AI_CONFIDENCE_THRESHOLD`) | `BaseAgent.run`; also rule GR-010 (`confidence < 0.75` → REQUIRE_HUMAN_REVIEW) |
| Evaluation pass | `overall ≥ 70` | `Evaluation.passed`; report check 8 flags sections below 70 |
| Block on unsupported numbers | any (`unsupported_numbers > 0`) | output guardrail CRITICAL finding → blocked; GR-011 BLOCK |
| Review when no sources | `not has_sources` | GR-012 REQUIRE_HUMAN_REVIEW |
| Block on prompt injection | `injection_detected` | GR-013 BLOCK (and input guardrail) |

---

## 2. The ten agents (`ai/agents/specialists.py`)

All agents are registered in `ai/agents/registry.py::AGENTS` and mirrored to the `agents` table at seed time. `narrative=False` agents do not call the provider at all.

| Code | Name | Responsibilities | Tools | Expert | Tasks / behaviour |
|---|---|---|---|---|---|
| `esg_data_agent` | ESG Data Agent | Understand incoming datasets, identify and classify fields, detect missing and inconsistent values, suggest mappings | search_metrics, search_knowledge_base, list_entities | document (no LLM) | `classify_dataset`: for each column, `search_metrics` top-3 → mapping with token-overlap confidence and alternatives; findings for missing `entity_code`/`period_code`, empty and non-numeric cells (first 500 rows). Used by `POST /datasets/classify`. |
| `calculation_agent` | ESG Calculation Agent | Identify required calculations, select approved formulas, explain them; never invents formulas or computes | calculate_metric, get_metric, get_metric_history, get_lineage, search_metrics | ghg | `explain`: metric codes from payload or regex on the question (falls back to `search_metrics` preferring derived kinds); for ≤4 metrics × ≤3 periods calls `calculate_metric` (persist=False) and `get_metric`; inputs become cited facts. |
| `standards_mapping_agent` | Standards Mapping Agent | Map metrics to frameworks, identify requirements and gaps, explain mapping decisions | get_framework_mapping, get_framework_requirement, search_knowledge_base, search_metrics | legal | `gap_analysis`: framework from payload/question keywords (`ifrs`, `gri`, `esrs`, `csrd`, `sasb`, `wef`, `ungc`, `sdg`) default WEF_SCM; coverage → missing/partial requirements with metric/evidence/narrative gap flags and recommendations; output includes the coverage disclaimer. |
| `materiality_agent` | Materiality Agent | Analyse material topics, support impact and financial materiality, produce recommendations with evidence | get_metric, get_metric_history, search_knowledge_base, get_open_issues | esg | `assess`: latest assessment; per-topic impact/financial scores as cited facts (`[KB-REPORT-2023 p.37-38]`); flags topics whose related metrics are unavailable; recommends elevating non-material topics with impact score ≥ 0.8 × threshold; always recommends adding financial-materiality scoring. |
| `evidence_agent` | Evidence Agent | Find evidence, link evidence to metrics, detect unsupported claims and evidence gaps | get_evidence, search_knowledge_base, get_metric, search_metrics, get_open_issues | data_quality | `review` / `find_gaps`: open `evidence_gap` issues; per metric evidence list and count; for metrics without evidence, suggests candidate report pages from the knowledge base. |
| `governance_agent` | Governance Agent | Check rules and policies, enforce approvals, detect violations, escalate critical events | run_governance_check, get_open_issues, get_report_readiness, search_knowledge_base | governance | `check`: triggered `metric_value` rules per metric, open/critical issue counts, `ESCALATE <issue>` list for CRITICAL issues. |
| `rag_research_agent` | RAG Research Agent | Retrieve approved ESG knowledge, policies, framework requirements, historical reports, internal documentation — permission-aware, cited | search_knowledge_base, search_metrics, get_metric, get_metric_history, get_framework_mapping, get_open_issues, get_report_readiness, get_evidence, calculate_metric, list_entities | esg | `answer`: metrics from codes or `search_metrics`; values for ≤6 metrics × ≤2 periods; history when the question mentions trend/change/why; knowledge passages; readiness when asked about publish/blocking; framework coverage when asked about gaps/coverage. Default agent of the Copilot. |
| `reporting_agent` | Reporting Agent | Assemble report sections, generate formal narratives referencing approved metrics and evidence, never fabricate | get_metric, get_metric_history, get_evidence, search_knowledge_base, get_framework_requirement | report_writing | `draft_section`: ≤20 metric values with citations and first evidence code, ≤5 requirement descriptions, ≤3 report passages matching the section title; prompt asks for 2–4 formal paragraphs with prior-period comparison and explicit "Data unavailable". Output key `narrative`. Used by `ReportBuilder._build_section`. |
| `evaluation_agent` | Evaluation Agent | Evaluate AI outputs for factual, numerical and citation consistency, framework compliance, hallucination; assign confidence | get_metric, search_knowledge_base | data_quality (no LLM) | `evaluate`: payload `text`, optional `facts`; metric codes found in the text are resolved through `get_metric`; runs the output guardrail and `score_output`; returns `evaluation`, `guardrail`, `confidence = overall/100`. |
| `assurance_agent` | Assurance Agent | Identify disclosure gaps, unsupported metrics, inconsistent calculations, unresolved issues; prepare assurance-ready packages | get_open_issues, get_report_readiness, get_framework_mapping, run_data_quality_check, get_evidence, get_lineage | risk | `package`: readiness components, per-framework alignment and missing/partial requirements, quality scores with `consistency < 100` (reported-vs-recalculated differences, YoY anomalies), all open issues → `package` dict. |

Payload conventions recognised by `gather`: `question`, `metric_codes`, `entity_code`, `period_code`, `periods`, `framework_code`, `frameworks`, `title`, `requirement_codes`, `columns`/`rows`, `text`/`facts`. Entity codes and `FY20xx` periods are also parsed from the question (`ENTITY_RE`, `PERIOD_RE`, `CODE_RE`).

---

## 3. Controlled tools (`ai/tools/registry.py`)

Every tool receives a `ToolContext(db, principal)`; lookups are tenant-scoped and `ToolContext.entity` enforces `Principal.entity_ids`. Default entity is the `group` entity, default period the latest non-future period. Numbers returned by tools are the only numbers the output guardrail accepts in narratives.

| Tool | Parameters | Returns |
|---|---|---|
| `get_metric` | metric_code, entity_code="", period_code="" | Value payload (`code, name, unit, pillar, topic, kind, entity, period, value, status, source_type, is_estimate, quality_score, evidence[], citation, data_unavailable, previous, previous_period`); falls back to consolidation of children |
| `get_metric_history` | metric_code, entity_code="" | Series across all periods + targets |
| `search_metrics` | query, limit=10 | Keyword-scored metric list (KPIs boosted) |
| `get_dataset` | dataset_code | Dataset + latest version metadata (hash, validation) |
| `get_evidence` | metric_code, entity_code="", period_code="" | Evidence items with printed/PDF pages and verification status |
| `get_framework_requirement` | requirement_code, period_code="" | `requirement_status` + framework code |
| `get_framework_mapping` | framework_code, period_code="" | Coverage summary (guidance stripped) |
| `calculate_metric` | metric_code, entity_code="", period_code="" | Deterministic calculation (persist=False) with formula, version, inputs, explanation |
| `run_data_quality_check` | metric_code, entity_code="", period_code="" | Seven dimension scores + explanation (persist=False) |
| `run_governance_check` | metric_code, entity_code="", period_code="" | Triggered `metric_value` rules |
| `get_lineage` | metric_code, entity_code="", period_code="" | Lineage graph |
| `search_knowledge_base` | query, limit=6, kind="" | Permission-filtered RAG hits with citations |
| `get_open_issues` | severity="", metric_code="", limit=20 | Open/acknowledged issues |
| `get_report_readiness` | period_code="", framework_codes="WEF_SCM,UNGC,UN_SDG" | Readiness overall, components, blocking issues |
| `list_entities` | — | Entities with consolidation settings |

`anthropic_tool_definitions(names)` exports the registry as strict JSON-schema tool definitions; `GET /agents/tools` exposes the same list. The current agents call tools from Python (`gather`) rather than through model-driven tool use, which keeps fact gathering deterministic and provider-independent.

---

## 4. Mixture-of-Experts router (`ai/moe/__init__.py`)

`classify(text, max_experts=2)` scores every expert by keyword hits (2 points for keywords longer than four characters, 1 otherwise; word-boundary or substring match). Experts scoring at least `max(1, top × 0.5)` are selected (at most two); with no hits the ESG expert is used (`method: "fallback"`). The router never fans out to every expert.

| Expert code | Name | Keywords (excerpt) | Tools | Executing agent |
|---|---|---|---|---|
| `esg` | ESG Expert | esg, sustainability, kpi, performance, overview, material | search_metrics, get_metric, get_metric_history, search_knowledge_base | rag_research_agent |
| `climate` | Climate Expert | climate, tcfd, paris, net zero, transition, physical risk, scenario, ifrs s2 | get_metric, get_framework_requirement, get_framework_mapping, search_knowledge_base | standards_mapping_agent |
| `ghg` | GHG Expert | ghg, emission, scope 1/2/3, co2, tco2e, carbon, energy, gj, intensity, renewable | get_metric, get_metric_history, calculate_metric, get_lineage, get_evidence | calculation_agent |
| `financial` | Financial Reporting Expert | revenue, ebitda, profit, tax, capex, dividend, wealth, economic value, pkr | get_metric, get_metric_history, calculate_metric | calculation_agent |
| `governance` | Governance Expert | board, director, ethics, corruption, whistleblow, speak out, code of conduct, committee, policy | get_metric, search_knowledge_base, get_framework_requirement | governance_agent |
| `risk` | Risk Expert | risk, issue, critical, blocking, readiness, ready to publish, what is missing, gap, preventing | get_open_issues, get_report_readiness, run_governance_check | assurance_agent |
| `legal` | Legal / Compliance Expert | gri, ifrs, issb, esrs, sasb, wef, ungc, sdg, framework, requirement, disclosure, coverage, alignment | get_framework_mapping, get_framework_requirement, search_knowledge_base | standards_mapping_agent |
| `data_quality` | Data Quality Expert | quality, evidence, lineage, source, traceab, missing data, anomal, inconsisten, validation, dataset | run_data_quality_check, get_evidence, get_lineage, get_dataset, get_open_issues | evidence_agent |
| `statistics` | Statistics Expert | trend, change, increase, decrease, yoy, compare, why did, benchmark, history | get_metric_history, get_metric, calculate_metric | calculation_agent |
| `document` | Document Intelligence Expert | extract, document, pdf, upload, classify, map fields, ingest, parse, table | search_knowledge_base, search_metrics | esg_data_agent |
| `report_writing` | Report Writing Expert | draft, narrative, write, section, report text, summary, generate | get_metric, get_metric_history, get_evidence, search_knowledge_base | reporting_agent |

Each expert carries a `system_hint` that is appended to the agent system prompt (for example the GHG expert: "Explain calculations; never compute numbers yourself — use calculate_metric"). `aggregate(responses)` orders responses by confidence, takes the first as primary, appends non-duplicate answers from the others, and unions sources and metrics.

---

## 5. Copilot flow (`ai/copilot.py`)

```
POST /copilot/ask {question, period_code, entity_code, frameworks}
  1. guardrails.check_input(question) → blocked? return status="blocked" with findings
  2. route = moe.classify(question)
  3. for each expert (≤2): agent = registry.get(expert.agent)(db, principal)
        task = {standards_mapping_agent: gap_analysis, calculation_agent: explain, evidence_agent: review,
                governance_agent: check, assurance_agent: package, materiality_agent: assess}.get(agent, "answer")
        result = agent.run(task, {question (sanitised), period_code, entity_code, frameworks}, expert_hint=expert.system_hint)
  4. merged = moe.aggregate([...])  → answer, confidence, sources, metrics_used, experts
  5. response adds: route, experts, relevant_frameworks (from source prefixes WEF/GRI/IFRS/ESRS/SASB/UNGC/SDG,
     else requested or default WEF_SCM,UNGC,UN_SDG), agent_runs (ids), guardrail, evidence codes,
     status = requires_review if any agent requires review else completed, disclaimer
```

The Copilot has no database access of its own; everything is delegated to agents and their tools. `GET /copilot/suggestions` lists ten seeded questions covering the demo (Scope 1 increase, incomplete WEF disclosures, missing evidence, highest risks, YoY changes, hazardous waste by entity, climate narrative draft, publication blockers, contractor TRIR calculation, IFRS S2 gaps).

---

## 6. Providers (`ai/llm/`)

### Interface

```python
class LLMProvider(Protocol):
    name: str
    model: str
    def complete(self, *, system: str, messages: list[dict], json_schema: dict | None = None,
                 max_tokens: int | None = None, effort: str | None = None, purpose: str = "general") -> LLMResult: ...
```

`LLMResult` carries `text, provider, model, prompt_tokens, completion_tokens, cache_read_tokens, latency_ms, stop_reason, parsed, error, refusal`; `ok` is true when there is no error and the stop reason is not `refusal`. `get_provider(name=None)` returns the configured provider (`ESG_AI_PROVIDER`), constructing `AnthropicProvider` lazily and degrading to `OfflineProvider` with a warning if the SDK or key is missing.

### Offline provider (`offline_provider.py`)

`OfflineProvider` (`model = deterministic-template-v1`) parses the `FACTS: {...}` JSON at the end of the user message and renders one sentence per metric: name, formatted value, unit, entity, period, percentage change against `previous`, and the citation; missing values become "Data unavailable … evidence required"; text facts are quoted; up to six sources are listed; report-section drafts end with a fixed provenance sentence. With no facts it returns a fixed "Data unavailable … human review required" sentence. Structured outputs are synthesised from the JSON schema (narrative keys get the narrative, `confidence` 0.9/0.2, arrays copied from facts where present). Because the output is a pure function of the facts it is used by the tests and by air-gapped deployments.

### Anthropic provider (`anthropic_provider.py`)

| Aspect | Implementation |
|---|---|
| SDK | `anthropic.Anthropic()` — credentials from `ANTHROPIC_API_KEY` (or the SDK's auth profile) |
| Model | `ESG_ANTHROPIC_MODEL` (default `claude-opus-5`) |
| Thinking | `thinking={"type": "adaptive"}` |
| Effort | `output_config.effort` = `ESG_ANTHROPIC_EFFORT` (`low|medium|high|xhigh|max`, default `high`) |
| Structured output | `output_config.format = {"type": "json_schema", "schema": …}` when the agent spec declares `output_schema`; the text is `json.loads`-ed into `LLMResult.parsed` |
| Streaming | `client.messages.stream(**kwargs)` then `get_final_message()` (avoids HTTP timeouts on long narratives) |
| Prompt caching | `cache_control: {"type": "ephemeral"}` on the system block; `cache_read_input_tokens` recorded |
| Max tokens | `ESG_ANTHROPIC_MAX_TOKENS` (default 16000) |
| Errors | `RateLimitError`, `AuthenticationError`, `BadRequestError`, `APIStatusError`, `APIConnectionError` → `LLMResult.error` (never raised); refusals surfaced as `refusal={category, explanation}` |
| Observability | Every call becomes a `model_runs` row (provider, model, purpose `<agent>:<task>`, tokens, latency, status, error) |

Provider failures never fail the request: the agent falls back to the offline template for that call and records `provider = "anthropic→offline"` on the run.

---

## 7. Guardrails (`ai/guardrails/__init__.py`)

| Check | Function | Detail |
|---|---|---|
| Prompt injection | `check_input` | Nine regex patterns (ignore previous instructions, reveal system prompt, jailbreak, `<system>`, developer mode, …) → HIGH finding, `injection_detected`, blocked |
| Sensitive data | `check_input`, `check_output` | API keys (`sk-…`, `AKIA…`), `password=`, card numbers, CNIC, JWTs → input blocked; output CRITICAL `confidentiality_leak`; `sanitized` text has matches replaced by `[REDACTED]` |
| Size | `check_input` | > 20,000 characters → MEDIUM finding |
| Upload format | `check_input(file_name=…)` | Allowed `.csv .xlsx .xls .json .pdf .txt .md`; otherwise HIGH, blocked |
| ESG value | `validate_esg_value(metric, value)` | Non-numeric for numeric types → HIGH `malformed`; `min`/`max` from `validation_rules` → HIGH `out_of_range`; percentage outside 0–100 → MEDIUM |
| Unsupported numbers | `check_output` | Every number token (years 1900–2100 and integers < 10 ignored) must be within 1 % / ±0.51 of a fact number or a ×10³/10⁶/10⁹ scaling within 2 % (`_close`) → otherwise CRITICAL, blocked |
| Missing citations | `check_output` | No `[...]` citation and no sources → MEDIUM |
| Compliance claim | `check_output` | `(fully|100%|completely)? compliant/compliance with GRI|IFRS|ISSB|ESRS|SASB|TCFD|WEF` → HIGH |
| Framework mismatch | `check_output(selected_frameworks=…)` | Mentions of frameworks outside the selected set → LOW |

---

## 8. Persisted artefacts

| Table | Written by | Content |
|---|---|---|
| `agent_runs` | `BaseAgent._persist` | task, input, output, status, confidence, sources, tools_used, guardrail_result (input+output), expert, provider, latency, evaluation_id |
| `model_runs` | `BaseAgent.run` | one per provider call |
| `evaluations` (`dimension="ai"`) | `BaseAgent._persist` | scores, overall, findings, passed |
| `audit_logs` | routers | `ai.generate` (agent run), `ai.copilot` (question excerpt, status, route) |

`GET /agents/runs/{id}` returns all of the above for one run; `GET /evaluations/summary` aggregates AI quality, hallucination rate, token usage, latency and guardrail blocks.
