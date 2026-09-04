import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useReports } from '@/api/reports';
import type { Report } from '@/api/types';
import { useAuth } from '@/app/auth';
import { Card, DataTable, ErrorBanner, PageHeader, ProgressBar, Select, StatusBadge, type Column } from '@/components/ui';
import { scoreHex } from '@/lib/colors';
import { fmtDateTime, fmtNumber } from '@/lib/format';

export function ReportsPage() {
  const { hasCap } = useAuth();
  const navigate = useNavigate();
  const [status, setStatus] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 25;
  const q = useReports({ status: status || undefined, limit, offset });
  const readiness = (r: Report) => (typeof r.readiness?.overall === 'number' ? (r.readiness.overall as number) : null);
  const cols: Column<Report>[] = [
    { key: 'id', header: '#', align: 'right' },
    { key: 'title', header: 'Report', render: (r) => <span className="font-medium">{r.title}</span> },
    { key: 'period_code', header: 'Period', render: (r) => r.period_code ?? '—' },
    { key: 'template_code', header: 'Template', render: (r) => <span className="font-mono text-xs">{r.template_code}</span> },
    { key: 'framework_codes', header: 'Frameworks', render: (r) => <span className="text-xs">{r.framework_codes.join(', ')}</span> },
    { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
    { key: 'sections', header: 'Sections approved', render: (r) => <span className="tabular-nums">{r.approved_sections ?? 0}/{r.section_count ?? 0}</span> },
    { key: 'readiness', header: 'Readiness', width: '160px', render: (r) => { const v = readiness(r); return v === null ? <span className="text-xs text-gray-400">Not validated</span> : <div className="flex items-center gap-2"><ProgressBar value={v} color={scoreHex(v)} className="flex-1" /><span className="text-xs tabular-nums">{fmtNumber(v, { decimals: 1 })}%</span></div>; } },
    { key: 'versions', header: 'Files', align: 'right', render: (r) => r.versions ?? 0 },
    { key: 'locked', header: 'Locked', render: (r) => (r.locked ? 'Yes' : 'No') },
    { key: 'created_at', header: 'Created', render: (r) => fmtDateTime(r.created_at) },
    { key: 'published_at', header: 'Published', render: (r) => fmtDateTime(r.published_at) },
  ];
  return (
    <div className="space-y-4">
      <PageHeader
        title="Generated Reports"
        description="Reports move through draft → ai_generated → requires_review → reviewed → approved → published. Open a report to preview pages, review sections and generate files."
        showScope={false}
        actions={
          <>
            <Select value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} className="w-44" aria-label="Status filter"><option value="">All statuses</option>{['draft', 'ai_generated', 'validating', 'requires_review', 'reviewed', 'approved', 'published', 'blocked'].map((s) => <option key={s} value={s}>{s}</option>)}</Select>
            {hasCap('report.build') && <Link to="/reports/builder" className="btn-primary">New report</Link>}
          </>
        }
      />
      {q.error && <ErrorBanner error={q.error} />}
      <Card bodyClassName="p-0">
        <DataTable columns={cols} rows={q.data?.items} rowKey={(r) => r.id} loading={q.isLoading} onRowClick={(r) => navigate(`/reports/${r.id}/preview`)} pagination={{ total: q.data?.total ?? 0, limit, offset, onChange: setOffset }} dense emptyTitle="No reports yet" emptyHint="Use the Report Builder to create one." />
      </Card>
    </div>
  );
}
