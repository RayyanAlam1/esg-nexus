export const UNAVAILABLE = 'Data unavailable';

const nf = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
const nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

/** Numbers with thousands separators and at most 2 decimals. null/undefined → "Data unavailable" (never 0). */
export function fmtNumber(v: number | null | undefined, opts: { decimals?: number; compact?: boolean } = {}): string {
  if (v === null || v === undefined || Number.isNaN(v)) return UNAVAILABLE;
  if (opts.compact && Math.abs(v) >= 1_000_000) {
    return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(v);
  }
  if (opts.decimals !== undefined) return new Intl.NumberFormat('en-US', { maximumFractionDigits: opts.decimals, minimumFractionDigits: 0 }).format(v);
  return Number.isInteger(v) ? nf0.format(v) : nf.format(v);
}

export function fmtValue(v: number | null | undefined, unit?: string | null): string {
  if (v === null || v === undefined) return UNAVAILABLE;
  const n = fmtNumber(v);
  if (!unit) return n;
  if (unit === '%') return `${n}%`;
  return `${n} ${unit}`;
}

export function fmtPct(v: number | null | undefined, signed = true): string {
  if (v === null || v === undefined || Number.isNaN(v)) return UNAVAILABLE;
  const s = fmtNumber(v, { decimals: 1 });
  return `${signed && v > 0 ? '+' : ''}${s}%`;
}

export function fmtScore(v: number | null | undefined): string {
  if (v === null || v === undefined) return UNAVAILABLE;
  return fmtNumber(v, { decimals: 1 });
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: '2-digit' });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('en-GB', { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function fmtDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return h > 0 ? `${h}h ${m}m` : m > 0 ? `${m}m ${s}s` : `${s}s`;
}

/** snake_case → Title Case */
export function titleCase(s: string | null | undefined): string {
  if (!s) return '—';
  return s
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function truncate(s: string | null | undefined, n = 120): string {
  if (!s) return '';
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}
