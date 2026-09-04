import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { AgentResult, DataSource, Dataset, DatasetDetail, DatasetRecord, LineageResponse, PageParams, Paginated, QualityScoreRow, QualitySummary, UploadResult } from './types';

export const listSources = () => api.get<DataSource[]>('/datasets/sources');
export const listDatasets = (f: PageParams & { source?: string; pillar?: string }) => api.get<Paginated<Dataset>>('/datasets', { ...f });
export const getDataset = (id: number) => api.get<DatasetDetail>(`/datasets/${id}`);
export const getRecords = (versionId: number, f: PageParams & { only_invalid?: boolean }) => api.get<Paginated<DatasetRecord>>(`/datasets/versions/${versionId}/records`, { ...f });
export const loadVersion = (versionId: number) => api.post<{ loaded_values: number; status: string }>(`/datasets/versions/${versionId}/load`);

export interface UploadFields {
  file: File;
  dataset_code: string;
  dataset_name?: string;
  source_code?: string;
  entity_default?: string;
  period_default?: string;
  auto_load?: boolean;
}
export const uploadDataset = (f: UploadFields) => {
  const fd = new FormData();
  fd.append('file', f.file);
  fd.append('dataset_code', f.dataset_code);
  if (f.dataset_name) fd.append('dataset_name', f.dataset_name);
  if (f.source_code) fd.append('source_code', f.source_code);
  if (f.entity_default) fd.append('entity_default', f.entity_default);
  if (f.period_default) fd.append('period_default', f.period_default);
  fd.append('auto_load', String(f.auto_load ?? true));
  return api.upload<UploadResult>('/datasets/upload', fd);
};
export const classifyColumns = (columns: string[], rows: Record<string, unknown>[] = []) => api.post<AgentResult>('/datasets/classify', { columns, rows });

export const getQualitySummary = (period?: string) => api.get<QualitySummary>('/quality/summary', { period });
export const listQualityScores = (f: PageParams & { period?: string; metric?: string; entity?: string; max_score?: number }) => api.get<Paginated<QualityScoreRow>>('/quality/scores', { ...f });
export const assessQuality = (period?: string) => api.post<{ assessed: number; average: number }>('/quality/assess', undefined, { period });

export const getLineage = (metric: string, scope: { entity?: string; period?: string }) => api.get<LineageResponse>('/lineage', { metric, ...scope });

export const useSources = () => useQuery({ queryKey: ['datasets', 'sources'], queryFn: listSources });
export const useDatasets = (f: PageParams & { source?: string; pillar?: string }) => useQuery({ queryKey: ['datasets', 'list', f], queryFn: () => listDatasets(f), placeholderData: (p) => p });
export const useDataset = (id: number | null) => useQuery({ queryKey: ['datasets', 'detail', id], queryFn: () => getDataset(id as number), enabled: id !== null });
export const useRecords = (versionId: number | null, f: PageParams & { only_invalid?: boolean }) =>
  useQuery({ queryKey: ['datasets', 'records', versionId, f], queryFn: () => getRecords(versionId as number, f), enabled: versionId !== null, placeholderData: (p) => p });
export const useQualitySummary = (period?: string) => useQuery({ queryKey: ['quality', 'summary', period], queryFn: () => getQualitySummary(period) });
export const useQualityScores = (f: PageParams & { period?: string; max_score?: number }) => useQuery({ queryKey: ['quality', 'scores', f], queryFn: () => listQualityScores(f), placeholderData: (p) => p });
export const useLineage = (metric: string | null, scope: { entity?: string; period?: string }) =>
  useQuery({ queryKey: ['lineage', metric, scope], queryFn: () => getLineage(metric as string, scope), enabled: !!metric });
