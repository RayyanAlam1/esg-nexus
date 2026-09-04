import { useQuery } from '@tanstack/react-query';
import { api, request } from './client';
import type { AdminUser, Notification, RoleDef, SystemInfo } from './types';

export const listUsers = () => api.get<AdminUser[]>('/admin/users');
export interface UserIn {
  email: string;
  full_name: string;
  password: string;
  roles: string[];
  entity_code?: string | null;
  title?: string | null;
}
export const createUser = (body: UserIn) => api.post<AdminUser>('/admin/users', body);
export const setUserRoles = (id: number, roles: string[]) => api.put<{ user_id: number; roles: string[] }>(`/admin/users/${id}/roles`, { roles });
export const listRoles = () => api.get<RoleDef[]>('/admin/roles');
export const getSystem = () => api.get<SystemInfo>('/admin/system');
export const reseed = () => api.post<Record<string, unknown>>('/admin/reseed');
export const listNotifications = (unread = false) => api.get<Notification[]>('/admin/notifications', { unread });

/** Health endpoints live outside the API prefix. */
export const getHealth = () => fetch('/health').then((r) => r.json() as Promise<{ status: string; app: string; uptime_seconds: number }>);
export const getReady = () => fetch('/health/ready').then((r) => r.json() as Promise<{ status: string; database?: string; tenants?: number; seeded?: boolean; error?: string }>);

export const useUsers = () => useQuery({ queryKey: ['admin', 'users'], queryFn: listUsers });
export const useRoles = () => useQuery({ queryKey: ['admin', 'roles'], queryFn: listRoles, staleTime: Infinity });
export const useSystem = () => useQuery({ queryKey: ['admin', 'system'], queryFn: getSystem });
export const useNotifications = () => useQuery({ queryKey: ['notifications'], queryFn: () => listNotifications(false), refetchInterval: 60_000 });
export const useHealth = () => useQuery({ queryKey: ['health'], queryFn: getHealth });
export const useReady = () => useQuery({ queryKey: ['health', 'ready'], queryFn: getReady });

export { request };
