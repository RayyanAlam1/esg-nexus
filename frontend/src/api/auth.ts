import { api } from './client';
import type { AuthUser, LoginResponse } from './types';

export const login = (email: string, password: string) => api.post<LoginResponse>('/auth/login', { email, password });
export const me = () => api.get<AuthUser>('/auth/me');
