import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { AgentResult, AgentRun, AgentRunDetail, AgentsResponse, CopilotAnswer, EvaluationRow, EvaluationSummary, EvaluationTrendPoint, KnowledgeDocument, PageParams, Paginated, RagResponse } from './types';

export const listAgents = () => api.get<AgentsResponse>('/agents');
export const listTools = () => api.get<{ name: string; description: string; schema: Record<string, unknown> }[]>('/agents/tools');
export const listRuns = (f: PageParams & { agent?: string; status?: string }) => api.get<Paginated<AgentRun>>('/agents/runs', { ...f });
export const getRun = (id: number) => api.get<AgentRunDetail>(`/agents/runs/${id}`);
export const runAgent = (code: string, task: string, payload: Record<string, unknown>) => api.post<AgentResult>(`/agents/${code}/run`, { task, payload });

export const askCopilot = (body: { question: string; period_code?: string | null; entity_code?: string | null; frameworks?: string[] | null }) => api.post<CopilotAnswer>('/copilot/ask', body);
export const getSuggestions = () => api.get<string[]>('/copilot/suggestions');
export const getExperts = () => api.get<{ code: string; name: string; description: string; agent: string; tools: string[] }[]>('/copilot/experts');

export const listDocuments = () => api.get<KnowledgeDocument[]>('/knowledge/documents');
export const searchKnowledge = (query: string, limit = 8, kind?: string) => api.post<RagResponse>('/knowledge/search', { query, limit, kind: kind || null });

export const listEvaluations = (f: PageParams & { dimension?: string; object_type?: string }) => api.get<Paginated<EvaluationRow>>('/evaluations', { ...f });
export const getEvaluationSummary = (period?: string) => api.get<EvaluationSummary>('/evaluations/summary', { period });
export const getEvaluationTrend = () => api.get<EvaluationTrendPoint[]>('/evaluations/trend');

export const useAgents = () => useQuery({ queryKey: ['agents'], queryFn: listAgents });
export const useRuns = (f: PageParams & { agent?: string; status?: string }) => useQuery({ queryKey: ['agents', 'runs', f], queryFn: () => listRuns(f), placeholderData: (p) => p });
export const useRun = (id: number | null) => useQuery({ queryKey: ['agents', 'run', id], queryFn: () => getRun(id as number), enabled: id !== null });
export const useSuggestions = () => useQuery({ queryKey: ['copilot', 'suggestions'], queryFn: getSuggestions, staleTime: Infinity });
export const useExperts = () => useQuery({ queryKey: ['copilot', 'experts'], queryFn: getExperts, staleTime: Infinity });
export const useDocuments = () => useQuery({ queryKey: ['knowledge', 'documents'], queryFn: listDocuments });
export const useEvaluations = (f: PageParams & { dimension?: string; object_type?: string }) => useQuery({ queryKey: ['evaluations', 'list', f], queryFn: () => listEvaluations(f), placeholderData: (p) => p });
export const useEvaluationSummary = (period?: string) => useQuery({ queryKey: ['evaluations', 'summary', period], queryFn: () => getEvaluationSummary(period) });
export const useEvaluationTrend = () => useQuery({ queryKey: ['evaluations', 'trend'], queryFn: getEvaluationTrend });
