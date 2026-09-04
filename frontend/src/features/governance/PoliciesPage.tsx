import { Link } from 'react-router-dom';
import { usePolicies } from '@/api/governance';
import type { GovernancePolicy } from '@/api/types';
import { Card, DataTable, ErrorBanner, PageHeader, StatusBadge, type Column } from '@/components/ui';
import { fmtDate, titleCase } from '@/lib/format';

export function PoliciesPage() {
  const q = usePolicies();
  const cols: Column<GovernancePolicy>[] = [
    { key: 'code', header: 'Code', render: (p) => <span className="font-mono text-xs text-navy">{p.code}</span> },
    { key: 'name', header: 'Policy', render: (p) => <span className="font-medium">{p.name}</span> },
    { key: 'category', header: 'Category', render: (p) => titleCase(p.category) },
    { key: 'owner', header: 'Owner', render: (p) => p.owner ?? '—' },
    { key: 'version', header: 'Version' },
    { key: 'effective_date', header: 'Effective', render: (p) => fmtDate(p.effective_date) },
    { key: 'status', header: 'Status', render: (p) => <StatusBadge status={p.status} /> },
    { key: 'evidence_code', header: 'Evidence', render: (p) => (p.evidence_code ? <Link to={`/evidence/${encodeURIComponent(p.evidence_code)}`} className="font-mono text-xs text-teal">{p.evidence_code}</Link> : '—') },
    { key: 'description', header: 'Description', render: (p) => <span className="text-xs text-gray-600">{p.description ?? '—'}</span> },
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Governance Policies" description="Corporate policies (ethics, HSE, data, reporting, tax, HR, security) that governance rules reference. Each policy links to its evidence document." showScope={false} />
      {q.error && <ErrorBanner error={q.error} />}
      <Card bodyClassName="p-0"><DataTable columns={cols} rows={q.data} rowKey={(p) => p.id} loading={q.isLoading} dense emptyTitle="No policies" /></Card>
    </div>
  );
}
