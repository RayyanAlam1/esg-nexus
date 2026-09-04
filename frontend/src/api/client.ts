/** Central fetch wrapper: bearer token, error envelope unwrapping, 401 redirect. */
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api/v1';

const TOKEN_KEY = 'esgnexus.token';
const REFRESH_KEY = 'esgnexus.refresh';
const USER_KEY = 'esgnexus.user';

export interface ApiErrorShape {
  status: number;
  code: string;
  message: string;
  details: unknown;
}

export class ApiError extends Error implements ApiErrorShape {
  status: number;
  code: string;
  details: unknown;
  constructor(status: number, code: string, message: string, details: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: (access: string, refresh?: string) => {
    localStorage.setItem(TOKEN_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
  },
  getUser: <T>(): T | null => {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  },
  setUser: (u: unknown) => localStorage.setItem(USER_KEY, JSON.stringify(u)),
};

export type QueryParams = Record<string, string | number | boolean | null | undefined>;

export function qs(params?: QueryParams): string {
  if (!params) return '';
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return;
    sp.set(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : '';
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  body?: unknown;
  formData?: FormData;
  query?: QueryParams;
  raw?: boolean;
}

function redirectToLogin() {
  tokenStore.clear();
  if (!window.location.pathname.startsWith('/login')) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.assign(`/login?next=${next}`);
  }
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE}${path}${qs(opts.query)}`;
  const headers: Record<string, string> = { Accept: 'application/json' };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.formData) {
    body = opts.formData;
  } else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(url, { method: opts.method ?? 'GET', headers, body });
  } catch (e) {
    throw new ApiError(0, 'network_error', 'Cannot reach the ESG Nexus API. Check that the backend is running.', String(e));
  }
  if (res.status === 401 && !path.startsWith('/auth/login')) {
    redirectToLogin();
    throw new ApiError(401, 'unauthorized', 'Session expired. Please sign in again.', null);
  }
  if (!res.ok) {
    let code = 'http_error';
    let message = `${res.status} ${res.statusText}`;
    let details: unknown = null;
    try {
      const payload = (await res.json()) as { error?: { code?: string; message?: string; details?: unknown } };
      if (payload?.error) {
        code = payload.error.code ?? code;
        message = payload.error.message ?? message;
        details = payload.error.details ?? null;
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, message, details);
  }
  if (res.status === 204) return undefined as T;
  if (opts.raw) return (await res.blob()) as unknown as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, query?: QueryParams) => request<T>(path, { query }),
  post: <T>(path: string, body?: unknown, query?: QueryParams) => request<T>(path, { method: 'POST', body, query }),
  put: <T>(path: string, body?: unknown, query?: QueryParams) => request<T>(path, { method: 'PUT', body, query }),
  del: <T>(path: string, query?: QueryParams) => request<T>(path, { method: 'DELETE', query }),
  upload: <T>(path: string, formData: FormData, query?: QueryParams) => request<T>(path, { method: 'POST', formData, query }),
};

/** Download a protected file: fetch with the bearer token, then trigger a browser save. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const blob = await request<Blob>(path, { raw: true });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
