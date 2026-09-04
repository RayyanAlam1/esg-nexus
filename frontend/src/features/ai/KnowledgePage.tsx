import { Link } from 'react-router-dom';
import { useDocuments } from '@/api/agents';
import type { KnowledgeDocument } from '@/api/types';
import { Card, DataTable, ErrorBanner, PageHeader, StatusBadge, type Column } from '@/components/ui';
import { fmtDate, titleCase } from '@/lib/format';

export function KnowledgePage() {
  const q = useDocuments();
  const cols: Column<KnowledgeDocument>[] = [
    { key: 'code', header: 'Code', render: (d) => <span className="font-mono text-xs text-navy">{d.code}</span> },
    { key: 'title', header: 'Title', render: (d) => <span className="font-medium">{d.title}</span> },
    { key: 'kind', header: 'Kind', render: (d) => titleCase(d.kind) },
    { key: 'version', header: 'Version' },
    { key: 'chunks', header: 'Chunks', align: 'right' },
    { key: 'freshness_date', header: 'Freshness', render: (d) => fmtDate(d.freshness_date) },
    { key: 'status', header: 'Status', render: (d) => <StatusBadge status={d.status} /> },
    { key: 'accessible', header: 'Access', render: (d) => <StatusBadge status={d.accessible ? 'verified' : 'rejected'} label={d.accessible ? 'Permitted' : 'Restricted'} /> },
    { key: 'permissions', header: 'Roles', render: (d) => <span className="text-xs text-gray-600">{((d.permissions?.roles as string[] | undefined) ?? ['*']).join(', ')}</span> },
    { key: 'source_ref', header: 'Source', render: (d) => <span className="text-xs text-gray-600">{d.source_ref ?? '—'}</span> },
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Knowledge Base" description="Approved documents indexed for permission-aware retrieval (frameworks, policies, methodology, reports, metric definitions)." showScope={false} actions={<Link to="/ai/rag" className="btn-secondary">RAG search</Link>} />
      {q.error && <ErrorBanner error={q.error} />}
      <Card bodyClassName="p-0">
        <DataTable columns={cols} rows={q.data} rowKey={(d) => d.id} loading={q.isLoading} dense emptyTitle="No knowledge documents" />
      </Card>
    </div>
  );
}
