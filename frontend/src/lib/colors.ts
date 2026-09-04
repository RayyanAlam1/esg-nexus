import type { Pillar, Severity } from '@/api/types';

/** Semantic severity colours (reserved — never reused for series). */
export const SEVERITY_HEX: Record<Severity, string> = {
  CRITICAL: '#B03A2E',
  HIGH: '#D9822B',
  MEDIUM: '#C9A227',
  LOW: '#2A78D6',
  INFO: '#6B7280',
};

export const SEVERITY_CLASSES: Record<Severity, string> = {
  CRITICAL: 'bg-red-50 text-[#8F2C22] border-red-200',
  HIGH: 'bg-orange-50 text-[#9A5A17] border-orange-200',
  MEDIUM: 'bg-amber-50 text-[#7A6215] border-amber-200',
  LOW: 'bg-blue-50 text-[#1E5AA6] border-blue-200',
  INFO: 'bg-gray-100 text-gray-700 border-gray-200',
};

export const SEVERITY_ORDER: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

/** Categorical palette (validated with the dataviz palette validator, all-pairs, light mode). Fixed order, never cycled. */
export const CATEGORICAL = ['#2a78d6', '#eb6834', '#1baf7a', '#4a3aa7'] as const;

export const PILLAR_HEX: Record<Pillar, string> = {
  environment: '#1baf7a',
  social: '#2a78d6',
  governance: '#4a3aa7',
  prosperity: '#eb6834',
};

export const PILLAR_LABEL: Record<Pillar, string> = {
  environment: 'Environment',
  social: 'Social',
  governance: 'Governance',
  prosperity: 'Prosperity',
};

/** Single-series mark colour (brand teal) and comparison/previous-period grey. */
export const SERIES_PRIMARY = '#1B7F79';
export const SERIES_PREVIOUS = '#9AA5B1';
export const SERIES_TARGET = '#0F2A44';
export const GRID = '#E5E9EE';
export const AXIS_TEXT = '#5B6470';

/** Status colours (good / warning / serious / critical) — with icon+label wherever used. */
export const STATUS_HEX = { good: '#1F7A3A', warning: '#C9A227', serious: '#D9822B', critical: '#B03A2E', neutral: '#6B7280' } as const;

export function scoreTone(v: number | null | undefined): keyof typeof STATUS_HEX {
  if (v === null || v === undefined) return 'neutral';
  if (v >= 80) return 'good';
  if (v >= 60) return 'warning';
  if (v >= 40) return 'serious';
  return 'critical';
}

export function scoreHex(v: number | null | undefined): string {
  return STATUS_HEX[scoreTone(v)];
}

export function scoreTextClass(v: number | null | undefined): string {
  switch (scoreTone(v)) {
    case 'good':
      return 'text-[#1F7A3A]';
    case 'warning':
      return 'text-[#7A6215]';
    case 'serious':
      return 'text-[#9A5A17]';
    case 'critical':
      return 'text-[#8F2C22]';
    default:
      return 'text-gray-500';
  }
}

/** Workflow/status badge classes. */
export function statusClass(status: string | null | undefined): string {
  const s = (status ?? '').toLowerCase();
  if (['approved', 'published', 'final', 'verified', 'complete', 'completed', 'resolved', 'on_track', 'active', 'ok', 'loaded', 'ready', 'passed', 'achieved'].includes(s))
    return 'bg-green-50 text-[#1F6B33] border-green-200';
  if (['requires_review', 'validating', 'reviewed', 'validated', 'partial', 'acknowledged', 'pending', 'ai_generated', 'normalized', 'received', 'exception_approved', 'not_set', 'target_not_set'].includes(s))
    return 'bg-amber-50 text-[#7A6215] border-amber-200';
  if (['blocked', 'rejected', 'missing', 'failed', 'error', 'open', 'unverified', 'above_target', 'below_target', 'off_target', 'missed', 'degraded', 'unavailable'].includes(s))
    return 'bg-red-50 text-[#8F2C22] border-red-200';
  if (['draft', 'omitted', 'no_target', 'retired', 'superseded', 'consolidated', 'not_derived', 'missing_inputs'].includes(s)) return 'bg-gray-100 text-gray-600 border-gray-200';
  return 'bg-navy-50 text-navy border-navy-100';
}

export function trendClass(trend: string | null | undefined): string {
  if (trend === 'improving') return 'text-[#1F7A3A]';
  if (trend === 'worsening') return 'text-[#8F2C22]';
  return 'text-gray-500';
}
