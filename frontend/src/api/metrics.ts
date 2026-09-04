import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { CalculationVersion, KpiCardData, MetricDefinition, MetricDetail, MetricValue, PageParams, Paginated, RecalculateResult, TargetRow, Target } from './types';

export interface MetricFilters extends PageParams {
  pillar?: string;
  topic?: string;
  kpi?: boolean;
  q?: string;
  kind?: string;
  framework?: string;
}

export const listMetrics = (f: MetricFilters) => api.get<Paginated<MetricDefinition>>('/metrics', { ...f });
export const getKpis = (scope: { period?: string; entity?: string; pillar?: string }) => api.get<{ period: string; entity: string; kpis: KpiCardData[] }>('/metrics/kpis', scope);
export const getMetricDetail = (code: string, scope: { period?: string; entity?: string }) => api.get<MetricDetail>(`/metrics/${encodeURIComponent(code)}/detail`, scope);
export const getMetricDefinition = (code: string) => api.get<MetricDefinition & { calculation_versions: CalculationVersion[] }>(`/metrics/${encodeURIComponent(code)}`);

export interface ValueIn {
  entity_code?: string | null;
  period_code: string;
  value_numeric?: number | null;
  value_text?: string | null;
  is_estimate?: boolean;
  confidence?: number | null;
  notes?: string | null;
  reason?: string | null;
  evidence_codes?: string[];
}
export const upsertValue = (code: string, body: ValueIn) => api.post<MetricValue & { guardrail_findings: unknown[] }>(`/metrics/${encodeURIComponent(code)}/values`, body);
export const setValueStatus = (code: string, body: { entity_code?: string | null; period_code: string; status: string; comment?: string | null }) =>
  api.post<MetricValue>(`/metrics/${encodeURIComponent(code)}/status`, body);
export const calculateMetric = (code: string, scope: { period?: string; entity?: string }) => api.post<Record<string, unknown>>(`/metrics/${encodeURIComponent(code)}/calculate`, undefined, scope);

export const listTargets = (status?: string) => api.get<TargetRow[]>('/targets', { status });
export interface TargetIn {
  metric_code: string;
  entity_code?: string | null;
  target_value?: number | null;
  baseline_value?: number | null;
  target_year?: number | null;
  direction: string;
  kind: string;
  description?: string | null;
  status: string;
}
export const createTarget = (body: TargetIn) => api.post<Target>('/targets', body);

export const listCalculationVersions = () => api.get<CalculationVersion[]>('/calculations/versions');
export const recalculate = (period?: string) => api.post<RecalculateResult>('/calculations/recalculate', undefined, { period });

export const useMetrics = (f: MetricFilters) => useQuery({ queryKey: ['metrics', 'list', f], queryFn: () => listMetrics(f), placeholderData: (p) => p });
export const useKpis = (scope: { period?: string; entity?: string; pillar?: string }) => useQuery({ queryKey: ['metrics', 'kpis', scope], queryFn: () => getKpis(scope) });
export const useMetricDetail = (code: string | undefined, scope: { period?: string; entity?: string }) =>
  useQuery({ queryKey: ['metrics', 'detail', code, scope], queryFn: () => getMetricDetail(code as string, scope), enabled: !!code });
export const useTargets = (status?: string) => useQuery({ queryKey: ['targets', status], queryFn: () => listTargets(status) });
export const useCalculationVersions = () => useQuery({ queryKey: ['calculations', 'versions'], queryFn: listCalculationVersions });
