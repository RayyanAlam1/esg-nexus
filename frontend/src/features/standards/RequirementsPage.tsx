import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useRequirements } from '@/api/frameworks';
import type { Requirement } from '@/api/types';
import { Card, DataTable, ErrorBanner, Input, PageHeader, type Column } from '@/components/ui';
import { titleCase } from '@/lib/format';

export function RequirementsPage() {
  const { code } = useParams();
  const q = useRequirements(code);
  const [filter, setFilter] = useState('');
  const rows = (q.data?.requirements ?? []).filter((r) => !filter || `${r.code} ${r.title} ${r.theme ?? ''} ${(r.metric_codes ?? []).join(' ')}`.toLowerCase().includes(filter.toLowerCase()));
  const byId = new Map((q.data?.requirements ?? []).map((r) => [r.id, r]));

  const cols: Column<Requirement>[] = [
    { key: 'code', header: 'Code', render: (r) => <span className={`font-mono text-xs ${r.parent_id ? 'pl-3 text-gray-700' : 'text-navy font-semibold'}`}>{r.code}</span> },
    { key: 'title', header: 'Requirement', render: (r) => <span className={r.parent_id ? '' : 'font-medium'}>{r.title}</span> },
    { key: 'parent', header: 'Parent', render: (r) => (r.parent_id ? byId.get(r.parent_id)?.code ?? '—' : '') },
    { key: 'pillar', header: 'Pillar', render: (r) => titleCase(r.pillar) },
    { key: 'theme', header: 'Theme', render: (r) => r.theme ?? '—' },
    { key: 'disclosure_type', header: 'Disclosure', render: (r) => r.disclosure_type },
    { key: 'is_core', header: 'Core', render: (r) => (r.is_core ? 'Core' : 'Expanded') },
    { key: 'evidence_required', header: 'Evidence', render: (r) => (r.evidence_required ? 'Required' : 'Optional') },
    { key: 'metric_codes', header: 'Default metrics', render: (r) => <div className="flex flex-wrap gap-1">{(r.metric_codes ?? []).map((m) => <Link key={m} to={`/metrics/${encodeURIComponent(m)}`} className="chip font-mono text-xxs hover:border-teal">{m}</Link>)}</div> },
    { key: 'guidance', header: 'Guidance', render: (r) => <span className="text-xs text-gray-600 line-clamp-2" title={r.guidance ?? ''}>{r.guidance ?? r.description ?? '—'}</span> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title={q.data ? `${q.data.framework.name} · v${q.data.version}` : `Framework ${code}`}
        description={q.data?.framework.description ?? undefined}
        showScope={false}
        actions={
          <>
            <Input placeholder="Filter requirements…" value={filter} onChange={(e) => setFilter(e.target.value)} className="w-64" aria-label="Filter requirements" />
            <Link to={`/standards/compliance?framework=${code}`} className="btn-primary btn-sm">Alignment view</Link>
          </>
        }
      />
      {q.error && <ErrorBanner error={q.error} />}
      <Card bodyClassName="p-0">
        <DataTable columns={cols} rows={rows} rowKey={(r) => r.id} loading={q.isLoading} dense emptyTitle="No requirements" />
      </Card>
    </div>
  );
}
