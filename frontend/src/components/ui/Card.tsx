import type { ReactNode } from 'react';
import { ArrowDownRight, ArrowUpRight, Minus, FileCheck, AlertCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { KpiCardData } from '@/api/types';
import { scoreTextClass, trendClass } from '@/lib/colors';
import { fmtNumber, fmtPct, fmtScore, UNAVAILABLE } from '@/lib/format';
import { cn } from '@/lib/utils';
import { StatusBadge } from './Badge';

export function Card({ title, actions, children, className, bodyClassName, subtitle }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClassName?: string; subtitle?: ReactNode }) {
  return (
    <section className={cn('card', className)}>
      {(title || actions) && (
        <header className="card-header">
          <div>
            <h3 className="card-title">{title}</h3>
            {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn('p-4', bodyClassName)}>{children}</div>
    </section>
  );
}

export function StatCard({ label, value, hint, tone, onClick, icon }: { label: string; value: ReactNode; hint?: ReactNode; tone?: string; onClick?: () => void; icon?: ReactNode }) {
  const Comp = onClick ? 'button' : 'div';
  return (
    <Comp onClick={onClick} className={cn('card p-3 text-left w-full', onClick && 'hover:border-teal focus:border-teal transition-colors')}>
      <div className="flex items-center justify-between">
        <span className="text-xxs uppercase tracking-wide text-gray-500 font-medium">{label}</span>
        {icon}
      </div>
      <div className={cn('text-xl font-semibold mt-1 tabular-nums', tone ?? 'text-navy')}>{value}</div>
      {hint && <div className="text-xs text-gray-500 mt-0.5">{hint}</div>}
    </Comp>
  );
}

function TrendIcon({ trend }: { trend: KpiCardData['trend'] }) {
  if (trend === 'flat') return <Minus size={14} aria-label="flat" />;
  if (trend === 'improving' || trend === 'up') return <ArrowUpRight size={14} aria-label={trend} />;
  return <ArrowDownRight size={14} aria-label={trend} />;
}

export function KpiCard({ kpi, compact }: { kpi: KpiCardData; compact?: boolean }) {
  const navigate = useNavigate();
  const targetLabel = kpi.target_status === 'no_target' ? null : kpi.target_status;
  return (
    <button
      type="button"
      onClick={() => navigate(`/metrics/${encodeURIComponent(kpi.code)}`)}
      className={cn('card text-left w-full p-3 hover:border-teal transition-colors flex flex-col', compact ? 'gap-1' : 'gap-1.5')}
      aria-label={`Open metric ${kpi.name}`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs text-gray-600 leading-4 line-clamp-2" title={kpi.name}>
          {kpi.name}
        </span>
        {kpi.is_kpi && <span className="badge bg-navy-50 text-navy border-navy-100">KPI</span>}
      </div>
      <div className="flex items-baseline gap-1.5">
        {kpi.value === null ? (
          <span className="text-sm font-medium text-gray-400 italic">{UNAVAILABLE}</span>
        ) : (
          <>
            <span className="text-lg font-semibold text-navy tabular-nums">{fmtNumber(kpi.value)}</span>
            {kpi.unit && <span className="text-xs text-gray-500">{kpi.unit}</span>}
          </>
        )}
        {kpi.is_estimate && <span className="text-xxs text-amber-700">est.</span>}
      </div>
      <div className="flex items-center gap-2 text-xs">
        {kpi.yoy_pct === null ? (
          <span className="text-gray-400">YoY —</span>
        ) : (
          <span className={cn('inline-flex items-center gap-0.5 tabular-nums', trendClass(kpi.trend))}>
            <TrendIcon trend={kpi.trend} />
            {fmtPct(kpi.yoy_pct)} <span className="text-gray-400 font-normal">vs {kpi.previous_period ?? 'prev.'}</span>
          </span>
        )}
      </div>
      {!compact && (
        <div className="flex items-center gap-2 mt-auto pt-1 text-xxs text-gray-500 flex-wrap">
          {targetLabel && <StatusBadge status={targetLabel} />}
          <span className="inline-flex items-center gap-0.5" title="Evidence links">
            <FileCheck size={11} aria-hidden="true" /> {kpi.evidence_count}
          </span>
          <span className={cn('tabular-nums', scoreTextClass(kpi.quality_score))} title="Quality score">
            Q {fmtScore(kpi.quality_score)}
          </span>
          {kpi.open_issues > 0 && (
            <span className="inline-flex items-center gap-0.5 text-[#9A5A17]" title="Open issues">
              <AlertCircle size={11} aria-hidden="true" /> {kpi.open_issues}
            </span>
          )}
        </div>
      )}
    </button>
  );
}
