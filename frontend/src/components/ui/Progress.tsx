import { scoreHex, scoreTextClass, SERIES_PRIMARY } from '@/lib/colors';
import { fmtScore, titleCase, UNAVAILABLE } from '@/lib/format';
import { cn } from '@/lib/utils';

export function ProgressBar({ value, color, className, height = 6, max = 100 }: { value: number | null | undefined; color?: string; className?: string; height?: number; max?: number }) {
  const pct = value === null || value === undefined ? 0 : Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className={cn('w-full bg-gray-100 rounded-sm overflow-hidden', className)} style={{ height }} role="progressbar" aria-valuenow={value ?? undefined} aria-valuemin={0} aria-valuemax={max}>
      <div style={{ width: `${pct}%`, background: color ?? SERIES_PRIMARY, height: '100%' }} />
    </div>
  );
}

/** Horizontal bars per dimension (quality dimensions, readiness components). */
export function DimensionBars({ data, onClick, labelWidth = 150, colorBy = 'score' }: { data: { key: string; label?: string; value: number | null }[]; onClick?: (key: string) => void; labelWidth?: number; colorBy?: 'score' | 'primary' }) {
  return (
    <ul className="space-y-1.5">
      {data.map((d) => {
        const Comp = onClick ? 'button' : 'div';
        return (
          <li key={d.key}>
            <Comp onClick={onClick ? () => onClick(d.key) : undefined} className={cn('flex items-center gap-3 w-full text-left', onClick && 'hover:bg-gray-50 rounded')}>
              <span className="text-xs text-gray-600 truncate" style={{ width: labelWidth }} title={d.label ?? titleCase(d.key)}>
                {d.label ?? titleCase(d.key)}
              </span>
              <ProgressBar value={d.value} color={colorBy === 'score' ? scoreHex(d.value) : SERIES_PRIMARY} className="flex-1" />
              <span className={cn('text-xs tabular-nums w-14 text-right', colorBy === 'score' ? scoreTextClass(d.value) : 'text-gray-700')}>{d.value === null ? '—' : fmtScore(d.value)}</span>
            </Comp>
          </li>
        );
      })}
    </ul>
  );
}

/** Ring gauge for 0–100 scores. */
export function ScoreRing({ value, size = 120, stroke = 10, label, sublabel, onClick }: { value: number | null | undefined; size?: number; stroke?: number; label?: string; sublabel?: string; onClick?: () => void }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = value === null || value === undefined ? 0 : Math.max(0, Math.min(100, value));
  const dash = (v / 100) * c;
  const Comp = onClick ? 'button' : 'div';
  return (
    <Comp onClick={onClick} className={cn('inline-flex flex-col items-center', onClick && 'hover:opacity-90')} aria-label={label ? `${label}: ${fmtScore(value)}` : undefined}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label ?? 'Score'} ${value === null || value === undefined ? UNAVAILABLE : fmtScore(value)}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#E5E9EE" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={scoreHex(value)}
          strokeWidth={stroke}
          strokeLinecap="butt"
          strokeDasharray={`${dash} ${c - dash}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" fontSize={size / 4.5} fontWeight={600} fill="#0F2A44">
          {value === null || value === undefined ? '—' : `${Math.round(value)}%`}
        </text>
      </svg>
      {label && <span className="text-xs font-medium text-gray-700 mt-1">{label}</span>}
      {sublabel && <span className="text-xxs text-gray-500">{sublabel}</span>}
    </Comp>
  );
}

export function ConfidenceBar({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-xs text-gray-400">Confidence —</span>;
  const pct = value <= 1 ? value * 100 : value;
  return (
    <div className="flex items-center gap-2 text-xs text-gray-600">
      <span>Confidence</span>
      <ProgressBar value={pct} color={scoreHex(pct)} className="w-28" />
      <span className={cn('tabular-nums', scoreTextClass(pct))}>{Math.round(pct)}%</span>
    </div>
  );
}
