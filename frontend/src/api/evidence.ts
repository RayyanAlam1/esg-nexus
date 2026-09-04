import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { EvidenceDetail, EvidenceGaps, EvidenceItem, PageParams, Paginated } from './types';

export interface EvidenceFilters extends PageParams {
  kind?: string;
  status?: string;
  q?: string;
  metric?: string;
}

export const listEvidence = (f: EvidenceFilters) => api.get<Paginated<EvidenceItem>>('/evidence', { ...f });
export const getEvidenceKinds = () => api.get<string[]>('/evidence/kinds');
export const getEvidence = (code: string) => api.get<EvidenceDetail>(`/evidence/${encodeURIComponent(code)}`);
export const getEvidenceGaps = (period?: string) => api.get<EvidenceGaps>('/evidence/gaps', { period });

export interface EvidenceIn {
  code: string;
  title: string;
  kind: string;
  source?: string | null;
  document_ref?: string | null;
  page_from?: number | null;
  page_to?: number | null;
  printed_page?: string | null;
  excerpt?: string | null;
  evidence_date?: string | null;
  entity_code?: string | null;
  period_code?: string | null;
  confidence?: number | null;
  metric_codes?: string[];
}
export const createEvidence = (body: EvidenceIn) => api.post<EvidenceItem>('/evidence', body);
export const linkEvidence = (code: string, body: { metric_code: string; entity_code?: string | null; period_code?: string | null; relation?: string; note?: string | null }) =>
  api.post<unknown>(`/evidence/${encodeURIComponent(code)}/link`, body);
export const verifyEvidence = (code: string, body: { status: string; comment?: string | null; confidence?: number | null }) =>
  api.post<EvidenceItem>(`/evidence/${encodeURIComponent(code)}/verify`, body);

export const useEvidenceList = (f: EvidenceFilters) => useQuery({ queryKey: ['evidence', 'list', f], queryFn: () => listEvidence(f), placeholderData: (p) => p });
export const useEvidenceKinds = () => useQuery({ queryKey: ['evidence', 'kinds'], queryFn: getEvidenceKinds, staleTime: Infinity });
export const useEvidence = (code: string | undefined) => useQuery({ queryKey: ['evidence', 'detail', code], queryFn: () => getEvidence(code as string), enabled: !!code });
export const useEvidenceGaps = (period?: string) => useQuery({ queryKey: ['evidence', 'gaps', period], queryFn: () => getEvidenceGaps(period) });
