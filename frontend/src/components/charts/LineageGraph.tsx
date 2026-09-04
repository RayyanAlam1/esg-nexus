import { useMemo, useState } from 'react';
import type { LineageGraph as Graph, LineageNode } from '@/api/types';
import { titleCase } from '@/lib/format';
import { cn } from '@/lib/utils';
import { EmptyState } from '../ui/EmptyState';
import { JsonViewer } from '../ui/JsonViewer';

const KIND_STYLE: Record<LineageNode['kind'], { fill: string; stroke: string; label: string }> = {
  metric: { fill: '#E3EAF2', stroke: '#0F2A44', label: 'Metric' },
  calculation: { fill: '#DDEFEE', stroke: '#1B7F79', label: 'Calculation' },
  input: { fill: '#F2F5F8', stroke: '#5B6470', label: 'Input' },
  dataset: { fill: '#FFF4E5', stroke: '#D9822B', label: 'Dataset' },
  source: { fill: '#FDF6E3', stroke: '#C9A227', label: 'Source' },
  evidence: { fill: '#EAF6EE', stroke: '#1F7A3A', label: 'Evidence' },
};

const NODE_W = 210;
const NODE_H = 44;
const COL_GAP = 70;
const ROW_GAP = 14;

/** Layered left-to-right graph: root metric → calculation → inputs → dataset → source → evidence. Click a node to inspect its metadata. */
export function LineageGraphView({ graph, onNodeClick, height }: { graph: Graph | null | undefined; onNodeClick?: (n: LineageNode) => void; height?: number }) {
  const [selected, setSelected] = useState<LineageNode | null>(null);
  const layout = useMemo(() => {
    if (!graph || !graph.nodes.length) return null;
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    const depth = new Map<string, number>();
    const root = graph.nodes[0];
    depth.set(root.id, 0);
    const queue = [root.id];
    while (queue.length) {
      const cur = queue.shift() as string;
      const d = depth.get(cur) ?? 0;
      for (const e of graph.edges) {
        if (e.from === cur && byId.has(e.to) && !depth.has(e.to)) {
          depth.set(e.to, d + 1);
          queue.push(e.to);
        }
      }
    }
    graph.nodes.forEach((n) => {
      if (!depth.has(n.id)) depth.set(n.id, 1);
    });
    // Evidence/dataset hang off the root: place them in the last columns so the flow reads left→right.
    const maxD = Math.max(...Array.from(depth.values()));
    const colOf = (n: LineageNode) => {
      const d = depth.get(n.id) ?? 0;
      if (n.kind === 'evidence') return maxD + 1;
      return d;
    };
    const cols = new Map<number, LineageNode[]>();
    graph.nodes.forEach((n) => {
      const c = colOf(n);
      cols.set(c, [...(cols.get(c) ?? []), n]);
    });
    const pos = new Map<string, { x: number; y: number }>();
    const colKeys = Array.from(cols.keys()).sort((a, b) => a - b);
    let maxRows = 0;
    colKeys.forEach((c, ci) => {
      const list = cols.get(c) ?? [];
      maxRows = Math.max(maxRows, list.length);
      list.forEach((n, ri) => pos.set(n.id, { x: 16 + ci * (NODE_W + COL_GAP), y: 16 + ri * (NODE_H + ROW_GAP) }));
    });
    const width = 32 + colKeys.length * (NODE_W + COL_GAP) - COL_GAP;
    const h = 32 + maxRows * (NODE_H + ROW_GAP) - ROW_GAP;
    return { pos, width, height: h, byId };
  }, [graph]);

  if (!graph || !graph.nodes.length || !layout) return <EmptyState compact title="Lineage unavailable" hint="No value is recorded for this metric in the selected scope, so there is nothing to trace." />;

  const select = (n: LineageNode) => {
    setSelected(n);
    onNodeClick?.(n);
  };

  return (
    <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
      <div className="overflow-auto border border-gray-200 rounded bg-white" style={{ maxHeight: height ?? 460 }}>
        <svg width={layout.width} height={layout.height} role="img" aria-label="Data lineage graph">
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
              <path d="M0,0 L8,4 L0,8 z" fill="#9AA5B1" />
            </marker>
          </defs>
          {graph.edges.map((e, i) => {
            const a = layout.pos.get(e.from);
            const b = layout.pos.get(e.to);
            if (!a || !b) return null;
            const x1 = a.x + NODE_W;
            const y1 = a.y + NODE_H / 2;
            const x2 = b.x;
            const y2 = b.y + NODE_H / 2;
            const mx = (x1 + x2) / 2;
            return (
              <g key={i}>
                <path d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`} fill="none" stroke="#9AA5B1" strokeWidth={1.5} markerEnd="url(#arrow)" />
                <text x={mx} y={(y1 + y2) / 2 - 4} fontSize={9} fill="#6B7280" textAnchor="middle">
                  {e.relation}
                </text>
              </g>
            );
          })}
          {graph.nodes.map((n) => {
            const p = layout.pos.get(n.id);
            if (!p) return null;
            const st = KIND_STYLE[n.kind] ?? KIND_STYLE.input;
            const active = selected?.id === n.id;
            return (
              <g key={n.id} transform={`translate(${p.x},${p.y})`} onClick={() => select(n)} className="cursor-pointer" role="button" tabIndex={0} aria-label={`${st.label}: ${n.label}`} onKeyDown={(ev) => ev.key === 'Enter' && select(n)}>
                <rect width={NODE_W} height={NODE_H} rx={4} fill={st.fill} stroke={active ? '#0F2A44' : st.stroke} strokeWidth={active ? 2 : 1} />
                <text x={8} y={15} fontSize={9} fill={st.stroke} fontWeight={600} style={{ textTransform: 'uppercase' }}>
                  {st.label}
                </text>
                <text x={8} y={31} fontSize={11} fill="#1F2937">
                  {n.label.length > 34 ? `${n.label.slice(0, 33)}…` : n.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <aside className="card p-3 text-xs">
        {selected ? (
          <>
            <div className="text-xxs uppercase tracking-wide text-gray-500 font-semibold">{KIND_STYLE[selected.kind]?.label ?? selected.kind}</div>
            <div className="font-medium text-navy mb-2 break-words">{selected.label}</div>
            <dl className="kv">
              {Object.entries(selected.meta ?? {}).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt>{titleCase(k)}</dt>
                  <dd className={cn(typeof v === 'string' && v.length > 60 ? 'text-xxs' : '')}>{v === null || v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd>
                </div>
              ))}
            </dl>
          </>
        ) : (
          <div className="text-gray-500">Select a node to inspect its metadata (value, status, hash, page reference, formula).</div>
        )}
        <details className="mt-3">
          <summary className="cursor-pointer text-teal">Raw graph</summary>
          <JsonViewer value={graph} maxHeight={200} />
        </details>
      </aside>
    </div>
  );
}
