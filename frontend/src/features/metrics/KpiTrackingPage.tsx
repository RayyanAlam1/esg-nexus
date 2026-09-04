import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useKpis } from '@/api/metrics';
import type { KpiCardData, Pillar } from '@/api/types';
import { useAppContext } from '@/app/context';
import { Card, DataTable, ErrorBanner, KpiCard, LoadingBlock, PageHeader, StatusBadge, Tabs, type Column } from '@/components/ui';
import { PILLAR_LABEL, scoreTextClass, trendClass } from '@/lib/colors';
import { fmtNumber, fmtPct, fmtScore } from '@/lib/format';
import { cn } from '@/lib/utils';

export function KpiTrackingPage() {
  const { scope } = useAppContext();
  const navigate = useNavigate();
  const [pillar, setPillar] = useState<string>('all');
  const [view, setView] = useState<'cards' | 'table'>('cards');
  const q = useKpis(scope);
  const all = q.data?.kpis ?? [];
  const rows = pillar === 'all' ? all : all.filter((k) => k.pillar === pillar);

  const cols: Column<KpiCardData>[] = [
    { key: 'code', header: 'Code', render: (k) => <span className="font-mono text-xs">{k.code}</span> },
    { key: 'name', header: 'KPI', render: (k) => <span className="font-medium">{k.name}</span> },
    { key: 'pillar', header: 'Pillar', render: (k) => PILLAR_LABEL[k.pillar as Pillar] ?? k.pillar },
    { key: 'value', header: 'Value', align: 'right', render: (k) => (k.value === null ? <span className="text-gray-400 italic">Data unavailable</span> : fmtNumber(k.value)) },
    { key: 'unit', header: 'Unit', render: (k) => k.unit ?? '' },
    { key: 'previous', header: 'Previous', align: 'right', render: (k) => fmtNumber(k.previous) },
    { key: 'yoy', header: 'YoY', align: 'right', render: (k) => <span className={cn('tabular-nums', trendClass(k.trend))}>{fmtPct(k.yoy_pct)}</span> },
    { key: 'target', header: 'Target', align: 'right', render: (k) => (k.target?.value !== null && k.target?.value !== undefined ? `${fmtNumber(k.target.value)}${k.target.year ? ` (${k.target.year})` : ''}` : '—') },
    { key: 'target_status', header: 'Target status', render: (k) => (k.target_status === 'no_target' ? <span className="text-gray-400">No target</span> : <StatusBadge status={k.target_status} />) },
    { key: 'evidence', header: 'Evidence', align: 'right', render: (k) => k.evidence_count },
    { key: 'quality', header: 'Quality', align: 'right', render: (k) => <span className={scoreTextClass(k.quality_score)}>{fmtScore(k.quality_score)}</span> },
    { key: 'issues', header: 'Issues', align: 'right', render: (k) => k.open_issues },
    { key: 'assurance', header: 'Assurance', render: (k) => k.assurance_status.replace(/_/g, ' ') },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="KPI Tracking"
        description="Key performance indicators with value, year-on-year movement, target status, evidence count and quality score."
        actions={
          <div className="flex gap-1">
            <button type="button" className={cn('btn-sm', view === 'cards' ? 'btn-primary' : 'btn-secondary')} onClick={() => setView('cards')}>Cards</button>
            <button type="button" className={cn('btn-sm', view === 'table' ? 'btn-primary' : 'btn-secondary')} onClick={() => setView('table')}>Table</button>
          </div>
        }
      />
      <Tabs
        tabs={[{ key: 'all', label: 'All', count: all.length }, ...(['environment', 'social', 'governance', 'prosperity'] as Pillar[]).map((p) => ({ key: p, label: PILLAR_LABEL[p], count: all.filter((k) => k.pillar === p).length }))]}
        active={pillar}
        onChange={setPillar}
      />
      {q.isLoading ? (
        <LoadingBlock lines={8} />
      ) : q.error ? (
        <ErrorBanner error={q.error} />
      ) : view === 'cards' ? (
        <div className="grid gap-3 grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
          {rows.map((k) => (
            <KpiCard key={k.code} kpi={k} />
          ))}
        </div>
      ) : (
        <Card bodyClassName="p-0">
          <DataTable columns={cols} rows={rows} rowKey={(k) => k.code} onRowClick={(k) => navigate(`/metrics/${encodeURIComponent(k.code)}`)} dense emptyTitle="No KPIs" />
        </Card>
      )}
    </div>
  );
}
