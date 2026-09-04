import { useQuery } from '@tanstack/react-query';
import { api, downloadFile } from './client';
import type { PageParams, Paginated, Report, ReportDetail, ReportPreview, ReportSection, ReportTemplate, ReportVersion, ValidationResult } from './types';

export const listTemplates = () => api.get<ReportTemplate[]>('/reports/templates');
export const listReports = (f: PageParams & { status?: string }) => api.get<Paginated<Report>>('/reports', { ...f });
export const getReport = (id: number) => api.get<ReportDetail>(`/reports/${id}`);
export interface ReportIn {
  period_code: string;
  template_code: string;
  title?: string | null;
  framework_codes: string[];
  scope?: Record<string, unknown> | null;
  org_id?: number | null;
}
export const createReport = (body: ReportIn) => api.post<ReportDetail>('/reports', body);
export const generateDraft = (id: number, sections?: string[]) => api.post<ReportDetail>(`/reports/${id}/generate-draft`, undefined, { sections: sections?.join(',') });
export const validateReport = (id: number) => api.post<ValidationResult>(`/reports/${id}/validate`);
export const getPreview = (id: number) => api.get<ReportPreview>(`/reports/${id}/preview`);
export const updateSection = (id: number, code: string, body: { state?: string | null; content_md?: string | null; comment?: string | null }) => api.put<ReportSection>(`/reports/${id}/sections/${code}`, body);
export const regenerateSection = (id: number, code: string) => api.post<ReportSection>(`/reports/${id}/sections/${code}/regenerate`);
export const transitionReport = (id: number, state: string, comment?: string) => api.post<ReportDetail>(`/reports/${id}/transition`, { state, comment: comment ?? null });
export const generateReport = (id: number, format: string, final = false) => api.post<ReportVersion>(`/reports/${id}/generate`, undefined, { format, final });
export const listVersions = (id: number) => api.get<ReportVersion[]>(`/reports/${id}/versions`);
export const downloadVersion = (v: ReportVersion) => downloadFile(`/reports/versions/${v.id}/download`, `report_${v.report_id}_v${v.version}${v.is_final ? '_final' : '_draft'}.${v.format}`);

export const useTemplates = () => useQuery({ queryKey: ['reports', 'templates'], queryFn: listTemplates, staleTime: Infinity });
export const useReports = (f: PageParams & { status?: string }) => useQuery({ queryKey: ['reports', 'list', f], queryFn: () => listReports(f), placeholderData: (p) => p });
export const useReport = (id: number | null) => useQuery({ queryKey: ['reports', 'detail', id], queryFn: () => getReport(id as number), enabled: id !== null });
export const usePreview = (id: number | null) => useQuery({ queryKey: ['reports', 'preview', id], queryFn: () => getPreview(id as number), enabled: id !== null });
