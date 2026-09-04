import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { login as apiLogin } from '@/api/auth';
import { tokenStore } from '@/api/client';
import type { AuthUser } from '@/api/types';

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  logout: () => void;
  hasCap: (cap: string) => boolean;
  hasRole: (...roles: string[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => (tokenStore.get() ? tokenStore.getUser<AuthUser>() : null));

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiLogin(email, password);
    tokenStore.set(res.access_token, res.refresh_token);
    tokenStore.setUser(res.user);
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    window.location.assign('/login');
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: !!user && !!tokenStore.get(),
      login,
      logout,
      hasCap: (cap: string) => !!user && (user.capabilities.includes(cap) || cap === 'read'),
      hasRole: (...roles: string[]) => !!user && roles.some((r) => user.roles.includes(r)),
    }),
    [user, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
