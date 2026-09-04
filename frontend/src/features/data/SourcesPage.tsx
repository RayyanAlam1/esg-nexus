import { useNavigate } from 'react-router-dom';
import { useSources } from '@/api/datasets';
import type { DataSource } from '@/api/types';
import { Card, DataTable, ErrorBanner, PageHeader, StatusBadge, type Column } from '@/components/ui';
import { fmtDate, titleCase } from '@/lib/format';

export function SourcesPage() {
  const q = useSources();
  const navigate = useNavigate();
  const cols: Column<DataSource>[] = [
    { key: 'code', header: 'Code', render: (s) => <span className="font-mono text-xs text-navy">{s.code}</span> },
    { key: 'name', header: 'Name', render: (s) => <span className="font-medium">{s.name}</span> },
    { key: 'kind', header: 'Kind', render: (s) => titleCase(s.kind) },
    { key: 'system_name', header: 'System', render: (s) => s.system_name ?? '—' },
    { key: 'owner', header: 'Owner', render: (s) => s.owner ?? '—' },
    { key: 'dataset_count', header: 'Datasets', align: 'right' },
    { key: 'is_active', header: 'Status', render: (s) => <StatusBadge status={s.is_active ? 'active' : 'retired'} /> },
    { key: 'description', header: 'Description', render: (s) => <span className="text-xs text-gray-600">{s.description ?? '—'}</span> },
    { key: 'created_at', header: 'Created', render: (s) => fmtDate(s.created_at) },
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Data Sources" description="Originating systems and documents (ERP, HR, EHS, environmental records, manual uploads). Click a source to see its datasets." showScope={false} />
      {q.error && <ErrorBanner error={q.error} />}
      <Card bodyClassName="p-0">
        <DataTable columns={cols} rows={q.data} rowKey={(s) => s.id} loading={q.isLoading} onRowClick={(s) => navigate(`/data/datasets?source=${encodeURIComponent(s.code)}`)} emptyTitle="No data sources" dense />
      </Card>
    </div>
  );
}
