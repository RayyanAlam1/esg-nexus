import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { EntityComparison, EsgTopic, Overview, PillarResponse } from './types';

export interface Scope {
  period?: string;
  entity?: string;
}

export const getOverview = (scope: Scope) => api.get<Overview>('/esg/overview', { ...scope });
export const getPillar = (pillar: string, scope: Scope, kpiOnly = false) => api.get<PillarResponse>(`/esg/pillar/${pillar}`, { ...scope, kpi_only: kpiOnly || undefined });
export const getEntityComparison = (metric: string, period?: string) => api.get<EntityComparison>('/esg/entity-comparison', { metric, period });
export const getTopics = () => api.get<EsgTopic[]>('/esg/topics');

export const useOverview = (scope: Scope) => useQuery({ queryKey: ['esg', 'overview', scope], queryFn: () => getOverview(scope) });
export const usePillar = (pillar: string, scope: Scope) => useQuery({ queryKey: ['esg', 'pillar', pillar, scope], queryFn: () => getPillar(pillar, scope) });
export const useEntityComparison = (metric: string | null, period?: string) =>
  useQuery({ queryKey: ['esg', 'entity-comparison', metric, period], queryFn: () => getEntityComparison(metric as string, period), enabled: !!metric });
export const useTopics = () => useQuery({ queryKey: ['esg', 'topics'], queryFn: getTopics, staleTime: 10 * 60_000 });
