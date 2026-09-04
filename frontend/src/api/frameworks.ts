import { useQueries, useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { AgentResult, Coverage, Framework, FrameworkMapping, Requirement, SelectedFramework } from './types';

export const listFrameworks = () => api.get<Framework[]>('/frameworks');
export const getRequirements = (code: string) => api.get<{ framework: Framework; version: string; requirements: Requirement[] }>(`/frameworks/${code}/requirements`);
export const getCoverage = (code: string, period?: string) => api.get<Coverage>(`/frameworks/${code}/coverage`, { period });
export const getSelected = (period?: string) => api.get<{ period: string; frameworks: SelectedFramework[] }>('/frameworks/selected', { period });
export const selectFrameworks = (framework_codes: string[], period_code: string) => api.post<{ selected: string[]; period: string }>('/frameworks/select', { framework_codes, period_code });
export const listMappings = () => api.get<FrameworkMapping[]>('/frameworks/mappings/all');
export interface MappingIn {
  requirement_code: string;
  metric_code?: string | null;
  mapping_type: string;
  rationale?: string | null;
  omission_reason?: string | null;
  confidence?: number | null;
}
export const createMapping = (body: MappingIn) => api.post<FrameworkMapping>('/frameworks/mappings', body);
export const gapAnalysis = (framework: string, period?: string) => api.post<AgentResult>('/frameworks/gap-analysis', undefined, { framework, period });

export const useFrameworks = () => useQuery({ queryKey: ['frameworks'], queryFn: listFrameworks, staleTime: 10 * 60_000 });
export const useRequirements = (code: string | undefined) => useQuery({ queryKey: ['frameworks', 'requirements', code], queryFn: () => getRequirements(code as string), enabled: !!code });
export const useCoverage = (code: string | null, period?: string) => useQuery({ queryKey: ['frameworks', 'coverage', code, period], queryFn: () => getCoverage(code as string, period), enabled: !!code });
export const useCoverages = (codes: string[], period?: string) =>
  useQueries({ queries: codes.map((c) => ({ queryKey: ['frameworks', 'coverage', c, period], queryFn: () => getCoverage(c, period) })) });
export const useSelectedFrameworks = (period?: string) => useQuery({ queryKey: ['frameworks', 'selected', period], queryFn: () => getSelected(period) });
export const useMappings = () => useQuery({ queryKey: ['frameworks', 'mappings'], queryFn: listMappings });
