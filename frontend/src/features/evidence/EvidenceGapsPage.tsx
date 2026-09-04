import { Link, useNavigate } from 'react-router-dom';
import { useEvidenceGaps } from '@/api/evidence';
import type { EvidenceGaps, Issue } from '@/api/types';
import { useAppContext } from '@/app/context';
import { Card, DataTable, ErrorBanner, LoadingBlock, PageHeader, ScoreRing, SeverityBadge, StatCard, StatusBadge, type Column } from '@/components/ui';
import { PILLAR_LABEL } from '@/lib/colors';
import { titleCase } from '@/lib/format';

type Gap = EvidenceGaps['gaps'][number];

export function EvidenceGapsPage() {
  const { period } = useAppContext();
  const navigate = useNavigate();
  const q = useEvidenceGaps(period);
  const gcols: Column<Gap>[] = [
    { key: 'severity', header: 'Severity', render: (g) => <SeverityBadge severity={g.severity} /> },
    { key: 'metric_code', header: 'Metric', render: (g) => <span className="font-mono text-xs text-navy">{g.metric_code}</span> },
    { key: 'metric_name', header: 'Name', render: (g) => <span className="font-medium">{g.metric_name}</span> },
    { key: 'pillar', header: 'Pillar', render: (g) => PILLAR_LABEL[g.pillar as keyof typeof PILLAR_LABEL] ?? g.pillar },
    { key: 'entity', header: 'Entity' },
    { key: 'period', header: 'Period' },
    { key: 'is_kpi', header: 'KPI', render: (g) => (g.is_kpi ? <span className="badge bg-navy-50 text-navy border-navy-100">KPI</span> : '') },
  ];
  const icols: Column<Issue>[] = [
    { key: 'severity', header: 'Severity', render: (i) => <SeverityBadge severity={i.severity} /> },
    { key: 'code', header: 'Code', render: (i) => <span className="font-mono text-xs">{i.code}</span> },
    { key: 'title', header: 'Issue', render: (i) => i.title },
    { key: 'metric_code', header: 'Metric', render: (i) => (i.metric_code ? <Link to={`/metrics/${encodeURIComponent(i.metric_code)}`} className="font-mono text-xs text-teal">{i.metric_code}</Link> : '—') },
    { key: 'status', header: 'Status', render: (i) => <StatusBadge status={i.status} /> },
    { key: 'required_action', header: 'Required action', render: (i) => <span className="text-xs text-[#8F2C22]">{i.required_action ?? '—'}</span> },
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Evidence Gaps" description="Evidence-required metric values without any linked evidence, plus unverified evidence and open evidence-gap issues." />
      {q.isLoading ? (
        <LoadingBlock />
      ) : q.error ? (
        <ErrorBanner error={q.error} />
      ) : q.data ? (
        <>
          <div className="grid gap-3 md:grid-cols-[180px_1fr]">
            <Card bodyClassName="flex items-center justify-center p-3"><ScoreRing value={q.data.coverage_pct} label="Evidence coverage" sublabel={q.data.period} /></Card>
            <div className="grid gap-2 grid-cols-2 md:grid-cols-4">
              <StatCard label="Values requiring evidence" value={q.data.required} />
              <StatCard label="Covered" value={q.data.covered} tone="text-[#1F7A3A]" />
              <StatCard label="Gaps" value={q.data.gaps.length} tone={q.data.gaps.length ? 'text-[#8F2C22]' : 'text-navy'} />
              <StatCard label="Unverified evidence" value={q.data.unverified_evidence} tone={q.data.unverified_evidence ? 'text-[#9A5A17]' : 'text-navy'} onClick={() => navigate('/evidence?status=unverified')} />
            </div>
          </div>
          <Card title={`Gaps (${q.data.gaps.length})`} bodyClassName="p-0" subtitle="Click a row to open the metric and link evidence">
            <DataTable columns={gcols} rows={q.data.gaps} rowKey={(g) => `${g.metric_code}-${g.entity}`} onRowClick={(g) => navigate(`/metrics/${encodeURIComponent(g.metric_code)}`)} dense emptyTitle="No evidence gaps" emptyHint="Every evidence-required value in this period is linked to evidence." />
          </Card>
          <Card title={`Open evidence issues (${q.data.open_issues.length})`} bodyClassName="p-0">
            <DataTable columns={icols} rows={q.data.open_issues} rowKey={(i) => i.id} onRowClick={(i) => navigate(`/governance/issues?q=${encodeURIComponent(i.code)}`)} dense emptyTitle="No open evidence issues" />
          </Card>
          <p className="text-xxs text-gray-400">{titleCase('category')}: evidence_gap issues are raised by the governance rules engine when an evidence-required value has no supporting evidence.</p>
        </>
      ) : null}
    </div>
  );
}
