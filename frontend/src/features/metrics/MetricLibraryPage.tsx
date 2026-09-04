import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTopics } from '@/api/esg';
import { useMetrics } from '@/api/metrics';
import type { MetricDefinition } from '@/api/types';
import { Card, DataTable, ErrorBanner, Input, PageHeader, Select, StatusBadge, type Column } from '@/components/ui';
import { PILLAR_LABEL } from '@/lib/colors';
import { titleCase } from '@/lib/format';
import { useDebounce } from '@/lib/utils';

const KINDS = ['raw', 'derived', 'ratio', 'intensity', 'percentage', 'yoy', 'aggregate', 'narrative', 'target'];

export function MetricLibraryPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounce(q, 300);
  const pillar = params.get('pillar') ?? '';
  const topic = params.get('topic') ?? '';
  const kind = params.get('kind') ?? '';
  const kpi = params.get('kpi') ?? '';
  const offset = Number(params.get('offset') ?? 0);
  const sort = params.get('sort') ?? undefined;
  const order = (params.get('order') as 'asc' | 'desc' | null) ?? undefined;
  const limit = 50;
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    if (k !== 'offset') p.delete('offset');
    setParams(p, { replace: true });
  };
  const topics = useTopics();
  const list = useMetrics({ pillar: pillar || undefined, topic: topic || undefined, kind: kind || undefined, kpi: kpi ? kpi === 'true' : undefined, q: dq || undefined, limit, offset, sort, order });

  const cols: Column<MetricDefinition>[] = [
    { key: 'code', header: 'Code', sortable: true, render: (m) => <span className="font-mono text-xs text-navy">{m.code}</span> },
    { key: 'name', header: 'Name', sortable: true, render: (m) => <span className="font-medium">{m.name}</span> },
    { key: 'pillar', header: 'Pillar', sortable: true, render: (m) => PILLAR_LABEL[m.pillar] ?? m.pillar },
    { key: 'topic_code', header: 'Topic', sortable: true, render: (m) => titleCase(m.topic_code) },
    { key: 'kind', header: 'Kind', sortable: true, render: (m) => <StatusBadge status={m.kind} /> },
    { key: 'unit', header: 'Unit', render: (m) => m.unit ?? '—' },
    { key: 'is_kpi', header: 'KPI', render: (m) => (m.is_kpi ? <span className="badge bg-navy-50 text-navy border-navy-100">KPI</span> : '') },
    { key: 'evidence_required', header: 'Evidence', render: (m) => (m.evidence_required ? 'Required' : 'Optional') },
    { key: 'assurance_status', header: 'Assurance', render: (m) => titleCase(m.assurance_status) },
    { key: 'applicable_frameworks', header: 'Frameworks', render: (m) => <span className="text-xs text-gray-600">{(m.applicable_frameworks ?? []).slice(0, 3).join(', ')}{(m.applicable_frameworks?.length ?? 0) > 3 ? ` +${(m.applicable_frameworks?.length ?? 0) - 3}` : ''}</span> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title="Metric Library" description="All active metric definitions with pillar, topic, kind, unit, evidence requirement and framework mapping." showScope={false} />
      <Card bodyClassName="p-3">
        <div className="grid gap-2 md:grid-cols-5">
          <Input placeholder="Search code, name, description…" value={q} onChange={(e) => { setQ(e.target.value); set('q', e.target.value); }} aria-label="Search metrics" />
          <Select value={pillar} onChange={(e) => set('pillar', e.target.value)} aria-label="Pillar">
            <option value="">All pillars</option>
            {Object.entries(PILLAR_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </Select>
          <Select value={topic} onChange={(e) => set('topic', e.target.value)} aria-label="Topic">
            <option value="">All topics</option>
            {(topics.data ?? []).filter((t) => !pillar || t.pillar === pillar).map((t) => (
              <option key={t.code} value={t.code}>{t.name}</option>
            ))}
          </Select>
          <Select value={kind} onChange={(e) => set('kind', e.target.value)} aria-label="Kind">
            <option value="">All kinds</option>
            {KINDS.map((k) => (
              <option key={k} value={k}>{titleCase(k)}</option>
            ))}
          </Select>
          <Select value={kpi} onChange={(e) => set('kpi', e.target.value)} aria-label="KPI filter">
            <option value="">KPIs and non-KPIs</option>
            <option value="true">KPIs only</option>
            <option value="false">Non-KPIs only</option>
          </Select>
        </div>
      </Card>
      {list.error && <ErrorBanner error={list.error} />}
      <Card bodyClassName="p-0">
        <DataTable
          columns={cols}
          rows={list.data?.items}
          rowKey={(m) => m.id}
          loading={list.isLoading}
          onRowClick={(m) => navigate(`/metrics/${encodeURIComponent(m.code)}`)}
          pagination={{ total: list.data?.total ?? 0, limit, offset, onChange: (o) => set('offset', String(o)) }}
          sort={{ sort, order, onChange: (s, o) => { set('sort', s); set('order', o); } }}
          emptyTitle="No metrics match the filters"
        />
      </Card>
    </div>
  );
}
