/** Shared response types mirroring the FastAPI routers (backend/app/api/v1). */
export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface PageParams {
  limit?: number;
  offset?: number;
  sort?: string;
  order?: 'asc' | 'desc';
}

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';
export type Pillar = 'environment' | 'social' | 'governance' | 'prosperity';

export interface AuthUser {
  id: number;
  email: string;
  full_name: string;
  tenant_id: number;
  tenant_slug?: string | null;
  roles: string[];
  capabilities: string[];
  title: string | null;
  /** Entity ids the user is restricted to. Empty means the whole organisation. */
  entity_ids?: number[];
  /** Entity codes matching `entity_ids`, for filtering selectors without another request. */
  entity_codes?: string[];
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: AuthUser;
}

export interface Organization {
  id: number;
  tenant_id: number;
  code: string;
  name: string;
  legal_name: string | null;
  legal_form: string | null;
  headquarters: string | null;
  country: string | null;
  stock_ticker: string | null;
  sector: string | null;
  description: string | null;
  reporting_boundary: string | null;
  website: string | null;
  contact: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
}

export interface ReportingPeriod {
  id: number;
  organization_id: number;
  code: string;
  label: string;
  granularity: string;
  start_date: string;
  end_date: string;
  status: string;
  is_baseline: boolean;
}

export interface EntityNode {
  id: number;
  code: string;
  name: string;
  kind: string;
  ownership_pct: number | null;
  consolidation_method: string;
  in_reporting_boundary: boolean;
  country: string | null;
  location: string | null;
  sector: string | null;
  attributes: Record<string, unknown>;
  children: EntityNode[];
}

export interface OrganizationDetail extends Organization {
  periods: ReportingPeriod[];
  entities: EntityNode[];
}

export interface TargetSummary {
  value: number | null;
  year: number | null;
  direction: string;
  status: string;
}

export interface KpiCardData {
  code: string;
  name: string;
  unit: string | null;
  pillar: Pillar;
  topic: string;
  kind: string;
  direction: string | null;
  value: number | null;
  previous: number | null;
  yoy_pct: number | null;
  trend: 'improving' | 'worsening' | 'up' | 'down' | 'flat';
  period: string;
  previous_period: string | null;
  target: TargetSummary | null;
  target_status: string;
  data_unavailable: boolean;
  source_type: string | null;
  is_estimate: boolean;
  evidence_count: number;
  quality_score: number | null;
  open_issues: number;
  assurance_status: string;
  is_kpi: boolean;
}

export interface Issue {
  id: number;
  code: string;
  severity: Severity;
  category: string;
  title: string;
  description: string | null;
  metric_code: string | null;
  entity_code: string | null;
  period_code: string | null;
  requirement_code: string | null;
  rule_code: string | null;
  status: 'open' | 'acknowledged' | 'resolved' | 'exception_approved';
  required_action: string | null;
  blocks_report: boolean;
  resolved_by: number | null;
  resolution_note: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at?: string;
}

export interface Readiness {
  overall: number;
  components: Record<string, number>;
  open_issues: Record<string, number>;
  blocking_issues: { code: string; severity: Severity; title: string; required_action: string | null; metric_code: string | null; entity_code: string | null }[];
  explanation: string[];
  ready_to_publish: boolean;
}

export interface Overview {
  organization: Organization;
  period: ReportingPeriod;
  entity: { code: string; name: string };
  readiness: Readiness;
  kpis: KpiCardData[];
  issues: { total: number; critical: number; high: number; top: Issue[] };
  coverage: { metric_definitions: number; values_in_period: number };
  what_changed: KpiCardData[];
}

export interface NarrativeMetric {
  code: string;
  name: string;
  text: string | null;
  data_unavailable: boolean;
}

export interface PillarTopic {
  code: string;
  name: string;
  description: string | null;
  metrics: KpiCardData[];
  narratives: NarrativeMetric[];
  kpis: KpiCardData[];
}

export interface PillarResponse {
  pillar: string;
  period: ReportingPeriod;
  entity: { code: string; name: string };
  topics: PillarTopic[];
}

export interface EntityComparison {
  metric: { code: string; name: string; unit: string | null };
  period: string;
  previous_period: string | null;
  entities: { entity: string; name: string; kind: string; value: number | null; previous: number | null; consolidation: string; in_boundary: boolean }[];
}

export interface EsgTopic {
  id: number;
  code: string;
  name: string;
  pillar: Pillar;
  description: string | null;
  sort_order: number;
  subtopics: { id: number; code: string; name: string }[];
}

export interface MetricDefinition {
  id: number;
  code: string;
  name: string;
  description: string | null;
  pillar: Pillar;
  topic_code: string;
  subtopic_code: string | null;
  unit: string | null;
  frequency: string;
  data_type: string;
  kind: string;
  calculation_method: string | null;
  formula: string | null;
  required_inputs: string[] | null;
  data_sources: string[] | null;
  evidence_required: boolean;
  evidence_requirements: string | null;
  applicable_frameworks: string[] | null;
  materiality_topic: string | null;
  assurance_status: string;
  validation_rules: Record<string, unknown> | null;
  aggregation: string;
  direction: string | null;
  tags: string[] | null;
  is_kpi: boolean;
  is_active: boolean;
  version: number;
  owner: string | null;
}

export interface FrameworkRequirementRef {
  code: string;
  title: string | null;
  framework: string;
  framework_name?: string;
  version?: string;
  pillar?: string | null;
  disclosure_type?: string;
}

export interface MetricValue {
  id: number;
  metric_id: number;
  entity_id: number;
  period_id: number;
  value_numeric: number | null;
  value_text: string | null;
  unit: string | null;
  status: string;
  source_type: string;
  dataset_version_id: number | null;
  calculation_run_id: number | null;
  quality_score: number | null;
  confidence: number | null;
  is_estimate: boolean;
  notes: string | null;
  created_by: number | null;
  approved_by: number | null;
  created_at: string;
  updated_at?: string;
}

export interface CalculationInput {
  value: number | null;
  metric_value_id?: number | null;
  entity?: string;
  period?: string;
  [k: string]: unknown;
}

export interface CalculationInfo {
  formula: string | null;
  version: string | null;
  status: string;
  result: number | null;
  inputs: Record<string, CalculationInput>;
  message: string | null;
  explanation: string | string[];
}

export interface EvidenceItem {
  id: number;
  code: string;
  title: string;
  kind: string;
  source: string | null;
  document_ref: string | null;
  page_from: number | null;
  page_to: number | null;
  printed_page: string | null;
  excerpt: string | null;
  evidence_date: string | null;
  owner_id: number | null;
  entity_id: number | null;
  period_id: number | null;
  verification_status: 'unverified' | 'verified' | 'rejected';
  verified_by: number | null;
  confidence: number | null;
  version: number;
  file_hash: string | null;
  storage_key: string | null;
  permissions: Record<string, unknown> | null;
  meta: Record<string, unknown> | null;
  created_at: string;
  relation?: string;
  link_count?: number;
}

export interface QualityInfo {
  scores: Record<string, number>;
  overall: number;
  explanation: string[] | null;
}

export interface GovernanceOutcome {
  rule: string;
  severity: Severity;
  action: string;
  message: string | null;
  required_action: string | null;
}

export interface LineageNode {
  id: string;
  kind: 'metric' | 'calculation' | 'input' | 'dataset' | 'source' | 'evidence';
  label: string;
  meta: Record<string, unknown>;
}

export interface LineageEdge {
  from: string;
  to: string;
  relation: string;
}

export interface LineageGraph {
  nodes: LineageNode[];
  edges: LineageEdge[];
}

export interface AuditEntry {
  id: number;
  user_id: number | null;
  action: string;
  object_type: string;
  object_id: string | null;
  old_value: unknown;
  new_value: unknown;
  reason: string | null;
  ip: string | null;
  created_at: string;
  user_email?: string | null;
}

export interface Target {
  id: number;
  metric_id: number;
  entity_id: number;
  target_year: number | null;
  baseline_value: number | null;
  target_value: number | null;
  direction: string;
  kind: string;
  description: string | null;
  owner: string | null;
  status: string;
  source_evidence_code: string | null;
}

export interface TargetRow extends Target {
  metric_code: string;
  metric_name: string;
  unit: string | null;
  entity_code: string;
  current_value: number | null;
  current_period: string;
  progress_pct: number | null;
}

export interface MetricDetail {
  metric: MetricDefinition & { framework_requirements: FrameworkRequirementRef[] };
  entity: { code: string; name: string; kind: string };
  period: string;
  card: KpiCardData;
  series: { period: string; value: number | null; status: string; source_type: string | null; text: string | null }[];
  value: MetricValue | null;
  calculation: CalculationInfo | null;
  evidence: EvidenceItem[];
  quality: QualityInfo | null;
  governance: GovernanceOutcome[];
  issues: Issue[];
  targets: Target[];
  lineage: LineageGraph;
  audit_history: AuditEntry[];
  ai_analysis: { available: boolean; endpoint: string; suggested_question: string };
}

export interface CalculationVersion {
  id: number;
  metric_id: number;
  version: string;
  formula: string;
  description: string | null;
  methodology_ref: string | null;
  is_current: boolean;
  approved_by: number | null;
  created_at: string;
  metric_code: string;
  metric_name: string;
}

export interface RecalculateResult {
  period: string;
  calculated: number;
  missing_inputs: number;
  errors: Record<string, unknown>[];
  governance: Record<string, unknown>;
}

export interface DataSource {
  id: number;
  organization_id: number;
  code: string;
  name: string;
  kind: string;
  description: string | null;
  owner: string | null;
  system_name: string | null;
  config: Record<string, unknown> | null;
  is_active: boolean;
  dataset_count: number;
  created_at: string;
}

export interface DatasetVersion {
  id: number;
  dataset_id: number;
  version: number;
  file_name: string | null;
  file_hash: string | null;
  storage_key: string | null;
  row_count: number;
  uploaded_by: number | null;
  uploaded_at: string;
  status: string;
  validation_result: Record<string, unknown> | null;
  transformation_history?: { step: string; at: string; [k: string]: unknown }[] | null;
  quality: Record<string, unknown> | null;
  idempotency_key: string | null;
}

export interface Dataset {
  id: number;
  source_id: number;
  code: string;
  name: string;
  description: string | null;
  period_id: number | null;
  entity_id: number | null;
  pillar: string | null;
  status: string;
  permissions: Record<string, unknown> | null;
  created_at: string;
  source_code?: string;
  source_name?: string;
  source_kind?: string;
  latest_version?: DatasetVersion | null;
  version_count?: number;
}

export interface DatasetDetail extends Dataset {
  source: DataSource;
  versions: DatasetVersion[];
}

export interface DatasetRecord {
  id: number;
  version_id: number;
  row_index: number;
  payload: Record<string, unknown>;
  metric_code: string | null;
  entity_code: string | null;
  period_code: string | null;
  value: number | null;
  value_text: string | null;
  unit: string | null;
  is_valid: boolean;
  issues: unknown[] | null;
  mapping_confidence: number | null;
}

export interface UploadResult {
  status: string;
  dataset_version_id?: number;
  version?: number;
  rows?: number;
  valid_rows?: number;
  loaded_values?: number;
  quality?: Record<string, unknown> | null;
  validation_result?: Record<string, unknown> | null;
  guardrail?: GuardrailResult;
}

export interface QualitySummary {
  period: string;
  overall: number;
  dimensions: Record<string, number>;
  assessed_values: number;
  by_pillar: Record<string, number>;
  lowest: { score: number; metric_code: string; metric_name: string; entity: string; explanation: string[] | null }[];
}

export interface QualityScoreRow {
  id: number;
  metric_id: number;
  entity_id: number;
  period_id: number;
  completeness: number;
  accuracy: number;
  consistency: number;
  timeliness: number;
  validity: number;
  uniqueness: number;
  traceability: number;
  overall: number;
  explanation: string[] | null;
  computed_at: string;
  metric_code: string;
  metric_name: string;
  entity_code: string;
}

export interface LineageResponse {
  graph: LineageGraph;
  chain: string[];
}

export interface Framework {
  id: number;
  code: string;
  name: string;
  publisher: string | null;
  description: string | null;
  jurisdiction: string | null;
  industry: string | null;
  is_custom: boolean;
  current_version: string | null;
  effective_date: string | null;
  requirement_count: number;
  versions: string[];
}

export interface Requirement {
  id: number;
  framework_version_id: number;
  parent_id: number | null;
  code: string;
  title: string;
  description: string | null;
  pillar: string | null;
  theme: string | null;
  disclosure_type: string;
  evidence_required: boolean;
  is_core: boolean;
  applicability: Record<string, unknown> | null;
  metric_codes: string[] | null;
  sort_order: number;
  guidance: string | null;
}

export interface RequirementStatus {
  code: string;
  title: string;
  pillar: string | null;
  theme: string | null;
  disclosure_type: string;
  is_core: boolean;
  status: 'complete' | 'partial' | 'missing' | 'omitted' | 'narrative_only';
  metrics: { code: string; name: string; has_value: boolean; has_evidence: boolean; kind: string; unit: string | null }[];
  evidence_gap: boolean;
  metric_gap: boolean;
  narrative_gap: boolean;
  omission_reason: string | null;
  description: string | null;
  guidance: string | null;
}

export interface Coverage {
  framework: string;
  framework_name?: string;
  version?: string;
  error?: string;
  alignment_pct: number;
  applicable?: number;
  completed?: number;
  partial?: number;
  missing?: number;
  omitted?: number;
  evidence_gaps?: number;
  metric_gaps?: number;
  narrative_gaps?: number;
  requirements: RequirementStatus[];
  disclaimer?: string;
}

export interface FrameworkMapping {
  id: number;
  requirement_id: number;
  metric_id: number | null;
  mapping_type: string;
  rationale: string | null;
  status: string;
  confidence: number | null;
  created_by: number | null;
  omission_reason: string | null;
  created_at: string;
  requirement_code: string;
  requirement_title: string;
  metric_code: string | null;
}

export interface SelectedFramework {
  id: number;
  organization_id: number;
  framework_version_id: number;
  period_id: number;
  applicable_scope: Record<string, unknown> | null;
  status: string;
  is_primary: boolean;
  framework_code: string;
  framework_name: string;
  version: string;
}

export interface MaterialityAssessment {
  id: number;
  organization_id: number;
  period_id: number;
  name: string;
  methodology: string | null;
  approach: string;
  threshold: number;
  status: string;
  evidence_codes: string[] | null;
  created_at: string;
  period_code: string;
  topics: number;
  material_topics: number;
}

export interface MaterialityTopic {
  id: number;
  assessment_id: number;
  topic_code: string;
  name: string;
  pillar: Pillar;
  impact_severity: number | null;
  impact_likelihood: number | null;
  impact_score: number | null;
  financial_magnitude: number | null;
  financial_likelihood: number | null;
  financial_score: number | null;
  stakeholder_priority: number | null;
  is_material: boolean;
  rationale: string | null;
  related_metric_codes: string[] | null;
  related_requirement_codes: string[] | null;
  risks: string[] | null;
  opportunities: string[] | null;
  evidence_codes: string[] | null;
  related_metrics: { code: string; name: string; unit: string | null; value: number | null; data_unavailable: boolean }[];
  x: number | null;
  y: number | null;
  size: number | null;
}

export interface StakeholderInput {
  id: number;
  assessment_id: number;
  stakeholder_group: string;
  topic_code: string | null;
  priority: number | null;
  channel: string | null;
  concern: string | null;
  engagement_value: string | null;
}

export interface MaterialityDetail extends Omit<MaterialityAssessment, 'topics' | 'material_topics'> {
  topics: MaterialityTopic[];
  stakeholder_inputs: StakeholderInput[];
  matrix: { x_axis: string; y_axis: string; threshold: number };
}

export interface EvidenceLinkRow {
  id: number;
  metric_code: string | null;
  metric_name: string | null;
  entity: string | null;
  period: string | null;
  value: number | null;
  relation: string;
  requirement_id: number | null;
}

export interface EvidenceDetail extends EvidenceItem {
  links: EvidenceLinkRow[];
}

export interface EvidenceGaps {
  period: string;
  required: number;
  covered: number;
  coverage_pct: number;
  gaps: { metric_code: string; metric_name: string; entity: string; period: string; is_kpi: boolean; pillar: string; severity: Severity }[];
  unverified_evidence: number;
  open_issues: Issue[];
}

export interface GuardrailResult {
  passed: boolean;
  blocked: boolean;
  injection_detected: boolean;
  missing_citations: boolean;
  unsupported_numbers: string[];
  findings: { severity?: string; message?: string; [k: string]: unknown }[];
}

export interface EvaluationResult {
  scores: Record<string, number>;
  overall: number;
  findings: string[] | null;
  passed: boolean;
}

export interface AgentSpec {
  code: string;
  name: string;
  description: string;
  responsibilities: string[];
  tools: string[];
  expert: string;
  version: string;
  is_active: boolean;
  runs: number;
  avg_confidence: number | null;
}

export interface AgentsResponse {
  agents: AgentSpec[];
  provider: string;
  model: string;
}

export interface AgentResult {
  agent: string;
  task: string;
  status: string;
  output: Record<string, unknown>;
  confidence: number;
  sources: string[];
  metrics_used: string[];
  tools_used: string[];
  guardrail: Record<string, unknown>;
  evaluation: EvaluationResult | null;
  governance: GovernanceOutcome[];
  run_id: number | null;
  provider: string | null;
  latency_ms: number;
  requires_human_review: boolean;
  blocked: boolean;
}

export interface AgentRun {
  id: number;
  agent_code: string;
  user_id: number | null;
  task: string;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  status: string;
  confidence: number | null;
  sources: string[] | null;
  tools_used: string[] | null;
  guardrail_result: Record<string, unknown> | null;
  evaluation_id: number | null;
  expert: string | null;
  provider: string | null;
  started_at: string;
  finished_at: string | null;
  latency_ms: number | null;
  error: string | null;
}

export interface ModelRun {
  id: number;
  agent_run_id: number | null;
  provider: string;
  model: string;
  purpose: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  cache_read_tokens: number;
  latency_ms: number | null;
  status: string;
  error: string | null;
  created_at: string;
}

export interface AgentRunDetail extends AgentRun {
  evaluation: (EvaluationResult & { id: number; object_type: string; object_id: string; created_at: string }) | null;
  model_runs: ModelRun[];
}

export interface CopilotAnswer {
  answer: string;
  confidence: number;
  sources: string[];
  metrics_used: string[];
  evidence?: string[];
  expert?: string;
  agent?: string;
  experts?: ({ code: string; name: string } | string)[];
  status: string;
  governance?: GovernanceOutcome[];
  evaluation?: EvaluationResult | null;
  requires_human_review?: boolean;
  extras?: Record<string, unknown>;
  route?: { primary: string; experts: string[]; scores: Record<string, number>; method: string } | null;
  relevant_frameworks?: string[];
  agent_runs?: (number | null)[];
  guardrail?: GuardrailResult;
  disclaimer?: string;
}

export interface KnowledgeDocument {
  id: number;
  code: string;
  title: string;
  kind: string;
  version: string;
  source_ref: string | null;
  freshness_date: string | null;
  permissions: Record<string, unknown> | null;
  status: string;
  meta: Record<string, unknown> | null;
  created_at: string;
  chunks: number;
  accessible: boolean;
}

export interface RagHit {
  citation: string;
  document: string;
  title: string;
  kind: string;
  score: number;
  text: string;
  meta: Record<string, unknown> | null;
  version: string;
  freshness: string | null;
}

export interface RagResponse {
  query: string;
  hits: RagHit[];
  index: string;
  permission_filtered: boolean;
}

export interface EvaluationRow {
  id: number;
  object_type: string;
  object_id: string;
  evaluator: string;
  dimension: string;
  scores: Record<string, number>;
  overall: number;
  findings: string[] | null;
  passed: boolean;
  created_at: string;
}

export interface EvaluationSummary {
  period: string;
  data_quality: { overall: number | null; completeness: number | null; accuracy: number | null; consistency: number | null };
  ai_quality: { overall: number | null; dimensions: Record<string, number>; evaluated_outputs: number; hallucination_rate: number | null | undefined };
  esg_quality: { framework_alignment: Record<string, number>; disclosure_completeness: number; evidence_coverage: number; metric_coverage: number };
  report_quality: { report_id: number; status: string; checks_passed: number; checks_total: number; structural_compliance: number | null } | null;
  readiness: { overall: number; components: Record<string, number> };
  overall_scores: { ai_quality: number | null; data_quality: number | null; evidence_coverage: number; framework_alignment: number; report_readiness: number };
  observability: { model_runs: number; prompt_tokens: number; completion_tokens: number; avg_model_latency_ms: number; guardrail_blocks: number };
}

export interface EvaluationTrendPoint {
  at: string;
  overall: number;
  object: string;
  scores: Record<string, number>;
}

export interface GovernancePolicy {
  id: number;
  code: string;
  name: string;
  category: string | null;
  description: string | null;
  owner: string | null;
  version: string;
  effective_date: string | null;
  status: string;
  evidence_code: string | null;
  external_ref: string | null;
}

export interface GovernanceRule {
  id: number;
  code: string;
  description: string;
  severity: Severity;
  scope: string;
  condition: string;
  action: string;
  message: string | null;
  required_action: string | null;
  owner: string | null;
  version: string;
  effective_date: string | null;
  approval_status: string;
  is_active: boolean;
  params: Record<string, unknown> | null;
  policy_code: string | null;
}

export interface RulesResponse {
  rules: GovernanceRule[];
  actions: string[];
  severities: Severity[];
  scopes: string[];
}

export interface RulesRunResult {
  evaluated?: number;
  triggered?: { issue: string; rule: string; severity: Severity; action: string; metric: string; entity: string }[];
  [k: string]: unknown;
}

export interface Approval {
  id: number;
  object_type: string;
  object_id: string;
  state: string;
  requested_by: number | null;
  assigned_to: number | null;
  decided_by: number | null;
  decision: string | null;
  comment: string | null;
  decided_at: string | null;
  context: Record<string, unknown> | null;
  created_at: string;
  requested_by_email?: string | null;
}

export interface ReportTemplateSection {
  code: string;
  title: string;
  level: number;
  source: string;
  metrics?: string[];
  requirements?: string[];
  [k: string]: unknown;
}

export interface ReportTemplate {
  code: string;
  name: string;
  description: string | null;
  sections: ReportTemplateSection[];
}

export interface ReportSection {
  id: number;
  report_id: number;
  code: string;
  title: string;
  sort_order: number;
  level: number;
  content_md: string | null;
  narrative_source: string;
  status: string;
  metric_codes: string[] | null;
  evidence_codes: string[] | null;
  requirement_codes: string[] | null;
  tables: unknown[] | null;
  charts: unknown[] | null;
  evaluation_id: number | null;
  agent_run_id: number | null;
  approved_by: number | null;
  version: number;
  comments: { at: string; by: string; state: string; note: string | null }[] | null;
}

export interface ReportVersion {
  id: number;
  report_id: number;
  version: number;
  format: string;
  storage_key: string;
  file_hash: string | null;
  size_bytes: number | null;
  generated_by: number | null;
  created_at: string;
  is_final: boolean;
}

export interface ValidationCheck {
  check: string;
  passed: boolean;
  detail: string;
  severity: string;
}

export interface ValidationResult {
  blocked: boolean;
  checks: ValidationCheck[];
  readiness: number | Record<string, unknown>;
  governance: GovernanceOutcome[];
  reason: string[];
  required_action: string[];
}

export interface Report {
  id: number;
  organization_id: number;
  period_id: number;
  template_code: string;
  title: string;
  framework_codes: string[];
  scope: Record<string, unknown> | null;
  status: string;
  readiness: Record<string, unknown> | null;
  validation_result: ValidationResult | null;
  created_by: number | null;
  approved_by: number | null;
  published_at: string | null;
  locked: boolean;
  created_at: string;
  updated_at?: string;
  period_code?: string;
  organization_name?: string;
  section_count?: number;
  approved_sections?: number;
  versions?: number;
}

export interface ReportDetail extends Omit<Report, 'versions'> {
  sections: ReportSection[];
  versions: ReportVersion[];
}

export interface ReportPage {
  number: number;
  title: string;
  html: string;
  code?: string;
  status?: string;
}

export interface ReportPreview {
  pages: ReportPage[];
  css: string;
  title: string;
  status: string;
  readiness: Record<string, unknown>;
}

export interface AdminUser {
  id: number;
  tenant_id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  title: string | null;
  created_at: string;
  roles: string[];
  entity_scope: string[];
}

export interface RoleDef {
  name: string;
  capabilities: string[];
}

export interface SystemInfo {
  app: string;
  environment: string;
  database: string;
  ai_provider: string;
  model: string;
  embedding_provider: string;
  tenant: { id: number; slug: string; name: string; deployment_model: string; is_active: boolean };
  uptime_seconds: number;
  python: string;
  counts: Record<string, number>;
  config: Record<string, unknown>;
}

export interface Notification {
  id: number;
  user_id: number | null;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  is_read: boolean;
  created_at: string;
}
