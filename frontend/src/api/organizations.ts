import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { EntityNode, Organization, OrganizationDetail, ReportingPeriod } from './types';

export const listOrganizations = () => api.get<Organization[]>('/organizations');
export const getOrganization = (id: number) => api.get<OrganizationDetail>(`/organizations/${id}`);
export const getEntities = (id: number) => api.get<EntityNode[]>(`/organizations/${id}/entities`);
export const getPeriods = (id: number) => api.get<ReportingPeriod[]>(`/organizations/${id}/periods`);

export const useOrganizations = () => useQuery({ queryKey: ['organizations'], queryFn: listOrganizations, staleTime: 5 * 60_000 });
export const useOrganization = (id: number | null) =>
  useQuery({ queryKey: ['organization', id], queryFn: () => getOrganization(id as number), enabled: id !== null, staleTime: 5 * 60_000 });

/** Flatten an entity tree into rows with depth for selectors and tables. */
export function flattenEntities(nodes: EntityNode[], depth = 0): (EntityNode & { depth: number })[] {
  return nodes.flatMap((n) => [{ ...n, depth }, ...flattenEntities(n.children ?? [], depth + 1)]);
}
