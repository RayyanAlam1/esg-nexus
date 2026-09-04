import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis, LabelList } from 'recharts';
import { AXIS_TEXT, GRID, SERIES_PREVIOUS, SERIES_PRIMARY } from '@/lib/colors';
import { fmtNumber, UNAVAILABLE } from '@/lib/format';
import { EmptyState } from '../ui/EmptyState';

export interface ComparisonRow {
  key: string;
  label: string;
  value: number | null;
  previous?: number | null;
  meta?: Record<string, unknown>;
}

interface Props {
  data: ComparisonRow[];
  unit?: string | null;
  height?: number;
  onBarClick?: (row: ComparisonRow) => void;
  currentLabel?: string;
  previousLabel?: string;
  layout?: 'vertical' | 'horizontal';
  showLabels?: boolean;
}

/** Horizontal comparison bars across entities (current vs previous). One axis; legend when two series. */
export function ComparisonBar({ data, unit, height, onBarClick, currentLabel = 'Current', previousLabel = 'Previous', layout = 'horizontal', showLabels = true }: Props) {
  const rows = data.filter((d) => d.value !== null || (d.previous !== null && d.previous !== undefined));
  if (!rows.length) return <EmptyState compact title={UNAVAILABLE} hint="No entity has a value for this metric in the selected period." />;
  const hasPrev = rows.some((d) => d.previous !== null && d.previous !== undefined);
  const h = height ?? Math.max(160, rows.length * 34 + 40);
  const horizontal = layout === 'horizontal';
  return (
    <div style={{ height: h }} className={onBarClick ? 'cursor-pointer' : undefined}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={rows}
          layout={horizontal ? 'vertical' : 'horizontal'}
          margin={{ top: 8, right: 48, bottom: 4, left: 8 }}
          barCategoryGap="28%"
          barGap={2}
          onClick={(s) => {
            const p = (s as { activePayload?: { payload: ComparisonRow }[] } | null)?.activePayload?.[0]?.payload;
            if (p && onBarClick) onBarClick(p);
          }}
        >
          <CartesianGrid stroke={GRID} horizontal={!horizontal} vertical={horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" tickFormatter={(v: number) => fmtNumber(v, { compact: true })} tick={{ fill: AXIS_TEXT, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="label" width={110} tick={{ fill: AXIS_TEXT, fontSize: 11 }} axisLine={{ stroke: GRID }} tickLine={false} />
            </>
          ) : (
            <>
              <XAxis dataKey="label" tick={{ fill: AXIS_TEXT, fontSize: 11 }} axisLine={{ stroke: GRID }} tickLine={false} />
              <YAxis tickFormatter={(v: number) => fmtNumber(v, { compact: true })} tick={{ fill: AXIS_TEXT, fontSize: 11 }} axisLine={false} tickLine={false} width={56} />
            </>
          )}
          <Tooltip
            cursor={{ fill: '#F2F5F8' }}
            formatter={(v, name) => [typeof v !== 'number' ? UNAVAILABLE : `${fmtNumber(v)}${unit ? ` ${unit}` : ''}`, String(name) === 'previous' ? previousLabel : currentLabel]}
            contentStyle={{ fontSize: 12, borderRadius: 4, borderColor: '#C9D2DC' }}
          />
          {hasPrev && <Legend iconType="square" iconSize={8} wrapperStyle={{ fontSize: 11 }} formatter={(v) => (v === 'previous' ? previousLabel : currentLabel)} />}
          {hasPrev && <Bar dataKey="previous" fill={SERIES_PREVIOUS} radius={horizontal ? [0, 3, 3, 0] : [3, 3, 0, 0]} maxBarSize={18} isAnimationActive={false} />}
          <Bar dataKey="value" fill={SERIES_PRIMARY} radius={horizontal ? [0, 3, 3, 0] : [3, 3, 0, 0]} maxBarSize={18} isAnimationActive={false}>
            {showLabels && <LabelList dataKey="value" position={horizontal ? 'right' : 'top'} formatter={(v: number | null) => (v === null || v === undefined ? '' : fmtNumber(v, { compact: true }))} style={{ fill: '#374151', fontSize: 10 }} />}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
