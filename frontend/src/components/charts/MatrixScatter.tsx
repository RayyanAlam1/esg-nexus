import { CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts';
import type { MaterialityTopic, Pillar } from '@/api/types';
import { AXIS_TEXT, GRID, PILLAR_HEX, PILLAR_LABEL } from '@/lib/colors';
import { fmtNumber } from '@/lib/format';
import { EmptyState } from '../ui/EmptyState';

interface Props {
  topics: MaterialityTopic[];
  threshold: number;
  onSelect?: (t: MaterialityTopic) => void;
  selected?: string | null;
  xLabel?: string;
  yLabel?: string;
  height?: number;
}

interface Point {
  x: number;
  y: number;
  z: number;
  name: string;
  pillar: Pillar;
  code: string;
  material: boolean;
  topic: MaterialityTopic;
}

function MatrixTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="bg-white border border-gray-300 rounded shadow-sm px-2.5 py-1.5 text-xs">
      <div className="font-semibold text-navy">{p.name}</div>
      <div className="text-gray-600">{PILLAR_LABEL[p.pillar] ?? p.pillar}</div>
      <div className="tabular-nums">Financial {fmtNumber(p.x)} · Impact {fmtNumber(p.y)}</div>
      <div className="tabular-nums">Stakeholder priority {fmtNumber(p.z)}</div>
      <div className={p.material ? 'text-[#1F7A3A]' : 'text-gray-500'}>{p.material ? 'Material' : 'Not material'}</div>
    </div>
  );
}

/** Double-materiality matrix: x financial, y impact, size stakeholder priority, colour by pillar, threshold lines. */
export function MatrixScatter({ topics, threshold, onSelect, selected, xLabel = 'Financial materiality', yLabel = 'Impact materiality', height = 420 }: Props) {
  const points: Point[] = topics
    .filter((t) => t.x !== null && t.y !== null)
    .map((t) => ({ x: t.x as number, y: t.y as number, z: t.size ?? 1, name: t.name, pillar: t.pillar, code: t.topic_code, material: t.is_material, topic: t }));
  if (!points.length) return <EmptyState title="Data unavailable" hint="No scored topics in this assessment." />;
  const pillars = Array.from(new Set(points.map((p) => p.pillar)));
  return (
    <div>
      <div style={{ height }} className="cursor-pointer">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 16, right: 24, bottom: 24, left: 8 }}>
            <CartesianGrid stroke={GRID} />
            <XAxis type="number" dataKey="x" domain={[0, 5]} tickCount={6} tick={{ fill: AXIS_TEXT, fontSize: 11 }} axisLine={{ stroke: GRID }} tickLine={false} label={{ value: xLabel, position: 'insideBottom', offset: -12, fontSize: 11, fill: AXIS_TEXT }} />
            <YAxis type="number" dataKey="y" domain={[0, 5]} tickCount={6} tick={{ fill: AXIS_TEXT, fontSize: 11 }} axisLine={false} tickLine={false} width={40} label={{ value: yLabel, angle: -90, position: 'insideLeft', fontSize: 11, fill: AXIS_TEXT }} />
            <ZAxis type="number" dataKey="z" range={[60, 400]} />
            <ReferenceLine x={threshold} stroke="#0F2A44" strokeDasharray="4 3" label={{ value: `Threshold ${threshold}`, position: 'top', fontSize: 10, fill: '#0F2A44' }} />
            <ReferenceLine y={threshold} stroke="#0F2A44" strokeDasharray="4 3" />
            <Tooltip content={<MatrixTooltip />} cursor={{ strokeDasharray: '3 3' }} />
            <Scatter data={points} onClick={(p) => onSelect?.((p as unknown as Point).topic)} isAnimationActive={false}>
              {points.map((p) => (
                <Cell key={p.code} fill={PILLAR_HEX[p.pillar] ?? '#6B7280'} fillOpacity={selected && selected !== p.code ? 0.35 : 0.85} stroke={selected === p.code ? '#0F2A44' : '#fff'} strokeWidth={selected === p.code ? 2 : 1} />
              ))}
              <LabelList dataKey="name" position="top" style={{ fontSize: 10, fill: '#374151' }} formatter={(v: string) => (v.length > 22 ? `${v.slice(0, 21)}…` : v)} />
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-wrap items-center gap-3 px-2 text-xs text-gray-600" aria-label="Legend">
        {pillars.map((p) => (
          <span key={p} className="inline-flex items-center gap-1">
            <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: PILLAR_HEX[p] }} aria-hidden="true" />
            {PILLAR_LABEL[p] ?? p}
          </span>
        ))}
        <span className="text-gray-400">· bubble size = stakeholder priority · dashed lines = materiality threshold</span>
      </div>
    </div>
  );
}
