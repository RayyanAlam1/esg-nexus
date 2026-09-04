import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { AgentResult, MaterialityAssessment, MaterialityDetail, MaterialityTopic, StakeholderInput } from './types';

export const listAssessments = () => api.get<MaterialityAssessment[]>('/materiality/assessments');
export const getAssessment = (id: number) => api.get<MaterialityDetail>(`/materiality/assessments/${id}`);
export interface TopicScoreIn {
  impact_severity?: number | null;
  impact_likelihood?: number | null;
  financial_magnitude?: number | null;
  financial_likelihood?: number | null;
  stakeholder_priority?: number | null;
  is_material?: boolean | null;
  rationale?: string | null;
}
export const updateTopic = (assessmentId: number, topicCode: string, body: TopicScoreIn) => api.put<MaterialityTopic>(`/materiality/assessments/${assessmentId}/topics/${topicCode}`, body);
export const addStakeholder = (assessmentId: number, body: { stakeholder_group: string; topic_code?: string | null; priority?: number | null; channel?: string | null; concern?: string | null }) =>
  api.post<StakeholderInput>(`/materiality/assessments/${assessmentId}/stakeholders`, body);
export const analyzeMateriality = (period?: string) => api.post<AgentResult>('/materiality/analyze', undefined, { period });

export const useAssessments = () => useQuery({ queryKey: ['materiality', 'assessments'], queryFn: listAssessments });
export const useAssessment = (id: number | null) => useQuery({ queryKey: ['materiality', 'assessment', id], queryFn: () => getAssessment(id as number), enabled: id !== null });
