import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { Approval, AuditEntry, GovernancePolicy, GovernanceRule, Issue, PageParams, Paginated, RulesResponse, RulesRunResult, Severity } from './types';

export const listPolicies = () => api.get<GovernancePolicy[]>('/governance/policies');
export const listRules = (scope?: string) => api.get<RulesResponse>('/governance/rules', { scope });
export interface RuleIn {
  code: string;
  description: string;
  severity: string;
  scope: string;
  condition: string;
  action: string;
  message?: string | null;
  required_action?: string | null;
  owner?: string | null;
  version?: string;
  approval_status?: string;
  policy_code?: string | null;
}
export const createRule = (body: RuleIn) => api.post<GovernanceRule>('/governance/rules', body);
export const updateRule = (code: string, body: Partial<Omit<RuleIn, 'code' | 'scope'>> & { is_active?: boolean }) => api.put<GovernanceRule>(`/governance/rules/${code}`, body);
export const testRule = (condition: string, context: Record<string, unknown>) => api.post<{ result?: boolean; error?: string }>('/governance/rules/test', { condition, context });
export const runRules = (period?: string) => api.post<RulesRunResult>('/governance/rules/run', undefined, { period });

export interface IssueFilters extends PageParams {
  severity?: string;
  status?: string;
  category?: string;
  metric?: string;
  period?: string;
}
export type IssuesPage = Paginated<Issue> & { open_by_severity: Record<Severity, number> };
export const listIssues = (f: IssueFilters) => api.get<IssuesPage>('/governance/issues', { ...f });
export const issueAction = (code: string, action: 'acknowledge' | 'resolve' | 'exception', comment?: string) => api.post<Issue>(`/governance/issues/${code}/${action}`, { comment: comment ?? null });

export const listApprovals = (pending = true) => api.get<Approval[]>('/governance/approvals', { pending });
export const decideApproval = (id: number, decision: string, comment?: string) => api.post<Approval>(`/governance/approvals/${id}/decide`, { decision, comment: comment ?? null });
export const requestApproval = (body: { object_type: string; object_id: string; assigned_to?: number | null; context?: Record<string, unknown> | null }) => api.post<Approval>('/governance/approvals', body);

export interface AuditFilters extends PageParams {
  action?: string;
  object_type?: string;
  object_id?: string;
  user_id?: number;
  q?: string;
  date_from?: string;
  date_to?: string;
}
export const listAudit = (f: AuditFilters) => api.get<Paginated<AuditEntry>>('/audit', { ...f });

export const usePolicies = () => useQuery({ queryKey: ['governance', 'policies'], queryFn: listPolicies });
export const useRules = (scope?: string) => useQuery({ queryKey: ['governance', 'rules', scope], queryFn: () => listRules(scope) });
export const useIssues = (f: IssueFilters) => useQuery({ queryKey: ['governance', 'issues', f], queryFn: () => listIssues(f), placeholderData: (p) => p });
export const useApprovals = (pending: boolean) => useQuery({ queryKey: ['governance', 'approvals', pending], queryFn: () => listApprovals(pending) });
export const useAudit = (f: AuditFilters) => useQuery({ queryKey: ['audit', f], queryFn: () => listAudit(f), placeholderData: (p) => p });
