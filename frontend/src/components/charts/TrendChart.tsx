import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Bar, BarChart, Legend } from 'recharts';
import { AXIS_TEXT, GRID, SERIES_PRIMARY, SERIES_PREVIOUS, SERIES_TARGET } from '@/lib/colors';
import { fmtNumber, UNAVAILABLE } from '@/lib/format';
import { EmptyState } from '../ui/EmptyState';

export interface TrendPoint {
  label: string;
  value: number | null;
  secondary?: number | null;
  meta?: Record<string, unknown>;
}

interface Props {
  data: TrendPoint[];
  unit?: string | null;
  height?: number;
  onPointClick?: (p: TrendPoint) => void;
  target?: number | null;
  targetLabel?: string;
  kind?: 'line' | 'bar';
  secondaryLabel?: string;
  primaryLabel?: string;
  compactAxis?: boolean;
}

function ChartTooltip({ active, payload, label, unit, primaryLabel, secondaryLabel }: { active?: boolean; payload?: { value: number | null; dataKey: string }[]; label?: string; unit?: string | null; primaryLabel?: string; secondaryLabel?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-300 rounded shadow-sm px-2.5 py-1.5 text-xs">
      <div className="font-semibold text-navy">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="tabular-nums text-gray-700">
          {p.dataKey === 'secondary' ? secondaryLabel ?? 'Previous' : primaryLabel ?? 'Value'}: {p.value === null || p.value === undefined ? UNAVAILABLE : `${fmtNumber(p.value)}${unit ? ` ${unit}` : ''}`}
        </div>
      ))}
    </div>
  );
}

/** Single-series trend (line) or comparison (bar). Click → drill-down callback. Honest empty state when no data. */
export function TrendChart({ data, unit, height = 220, onPointClick, target, targetLabel = 'Target', kind = 'line', secondaryLabel, primaryLabel, compactAxis }: Props) {
  const hasData = data.some((d) => d.value !== null && d.value !== undefined);
  if (!hasData) return <EmptyState compact title={UNAVAILABLE} hint="No values recorded for the selected scope." />;
  const hasSecondary = data.some((d) => d.secondary !== null && d.secondary !== undefined);
  const fmtAxis = (v: number) => fmtNumber(v, { compact: true });
  const common = {
    data,
    margin: { top: 12, right: 16, bottom: 4, left: 4 },
    onClick: (s: { activePayload?: { payload: TrendPoint }[] } | null) => {
      const p = s?.activePayload?.[0]?.payload;
      if (p && onPointClick) onPointClick(p);
    },
  };
  return (
    <div style={{ height }} className={onPointClick ? 'cursor-pointer' : undefined}>
      <ResponsiveContainer width="100%" height="100%">
        {kind === 'bar' ? (
          <BarChart {...common} barCategoryGap="30%" barGap={2}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: AXIS_TEXT, fontSize: 11 }} axisLine={{ stroke: GRID }} tickLine={false} interval={compactAxis ? 'preserveStartEnd' : 0} />
            <YAxis tickFormatter={fmtAxis} tick={{ fill: AXIS_TEXT, fontSize: 11 }} axisLine={false} tickLine={false} width={56} />
            <Tooltip content={<ChartTooltip unit={unit} primaryLabel={primaryLabel} secondaryLabel={secondaryLabel} />} cursor={{ fill: '#F2F5F8' }} />
            {hasSecondary && <Legend iconType="square" iconSize={8} wrapperStyle={{ fontSize: 11 }} formatter={(v) => (v === 'secondary' ? secondaryLabel ?? 'Previous' : primaryLabel ?? 'Current')} />}
            {hasSecondary && <Bar dataKey="secondary" fill={SERIES_PREVIOUS} radius={[3, 3, 0, 0]} maxBarSize={28} isAnimationActive={false} />}
            <Bar dataKey="value" fill={SERIES_PRIMARY} radius={[3, 3, 0, 0]} maxBarSize={28} isAnimationActive={false} />
            {target !== null && target !== undefined && <ReferenceLine y={target} stroke={SERIES_TARGET} strokeDasharray="4 3" label={{ value: targetLabel, position: 'insideTopRight', fontSize: 10, fill: SERIES_TARGET }} />}
          </BarChart>
        ) : (
          <LineChart {...common}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: AXIS_TEXT, fontSize: 11 }} axisLine={{ stroke: GRID }} tickLine={false} />
            <YAxis tickFormatter={fmtAxis} tick={{ fill: AXIS_TEXT, fontSize: 11 }} axisLine={false} tickLine={false} width={56} domain={['auto', 'auto']} />
            <Tooltip content={<ChartTooltip unit={unit} primaryLabel={primaryLabel} secondaryLabel={secondaryLabel} />} cursor={{ stroke: GRID }} />
            {hasSecondary && <Legend iconType="plainline" iconSize={12} wrapperStyle={{ fontSize: 11 }} formatter={(v) => (v === 'secondary' ? secondaryLabel ?? 'Previous' : primaryLabel ?? 'Current')} />}
            {hasSecondary && <Line type="monotone" dataKey="secondary" stroke={SERIES_PREVIOUS} strokeWidth={2} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />}
            <Line type="monotone" dataKey="value" stroke={SERIES_PRIMARY} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: '#fff' }} activeDot={{ r: 6 }} connectNulls={false} isAnimationActive={false} />
            {target !== null && target !== undefined && <ReferenceLine y={target} stroke={SERIES_TARGET} strokeDasharray="4 3" label={{ value: targetLabel, position: 'insideTopRight', fontSize: 10, fill: SERIES_TARGET }} />}
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
