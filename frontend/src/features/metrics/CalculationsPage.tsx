import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Play } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { recalculate, useCalculationVersions } from '@/api/metrics';
import type { CalculationVersion, RecalculateResult } from '@/api/types';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { Card, DataTable, ErrorBanner, Input, JsonDetails, PageHeader, StatCard, StatusBadge, type Column } from '@/components/ui';
import { fmtDate } from '@/lib/format';

export function CalculationsPage() {
  const { period } = useAppContext();
  const { hasCap } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const versions = useCalculationVersions();
  const [q, setQ] = useState('');
  const [result, setResult] = useState<RecalculateResult | null>(null);
  const run = useMutation({
    mutationFn: () => recalculate(period),
    onSuccess: (r) => {
      setResult(r);
      qc.invalidateQueries({ queryKey: ['metrics'] });
      qc.invalidateQueries({ queryKey: ['esg'] });
    },
  });
  const rows = (versions.data ?? []).filter((v) => !q || `${v.metric_code} ${v.metric_name} ${v.formula}`.toLowerCase().includes(q.toLowerCase()));

  const cols: Column<CalculationVersion>[] = [
    { key: 'metric_code', header: 'Metric', render: (v) => <span className="font-mono text-xs text-navy">{v.metric_code}</span> },
    { key: 'metric_name', header: 'Name', render: (v) => v.metric_name },
    { key: 'version', header: 'Version', render: (v) => v.version },
    { key: 'formula', header: 'Formula', render: (v) => <code className="text-xs bg-gray-50 px-1 rounded">{v.formula}</code> },
    { key: 'description', header: 'Description', render: (v) => <span className="text-xs text-gray-600">{v.description ?? '—'}</span> },
    { key: 'is_current', header: 'Current', render: (v) => <StatusBadge status={v.is_current ? 'active' : 'superseded'} label={v.is_current ? 'Current' : 'Superseded'} /> },
    { key: 'created_at', header: 'Created', render: (v) => fmtDate(v.created_at) },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Calculations"
        description="Versioned, approved formulas for derived metrics. Recalculation re-runs every formula for the selected period, re-assesses data quality and re-evaluates governance rules."
        actions={
          hasCap('metric.write') && (
            <button type="button" className="btn-primary" onClick={() => run.mutate()} disabled={run.isPending}>
              <Play size={14} /> {run.isPending ? 'Recalculating…' : `Recalculate ${period}`}
            </button>
          )
        }
      />
      {run.error ? <ErrorBanner error={run.error} /> : null}
      {result && (
        <Card title={`Recalculation result · ${result.period}`}>
          <div className="grid gap-2 grid-cols-2 md:grid-cols-4">
            <StatCard label="Calculated" value={result.calculated} tone="text-[#1F7A3A]" />
            <StatCard label="Missing inputs" value={result.missing_inputs} tone={result.missing_inputs ? 'text-[#9A5A17]' : 'text-navy'} />
            <StatCard label="Errors" value={result.errors.length} tone={result.errors.length ? 'text-[#8F2C22]' : 'text-navy'} />
            <StatCard label="Rules triggered" value={String((result.governance as { triggered_count?: number; created?: number }).created ?? Object.keys(result.governance).length)} hint="Governance summary" />
          </div>
          {result.errors.length > 0 && <JsonDetails label="Error details" value={result.errors} />}
          <JsonDetails label="Governance summary" value={result.governance} />
        </Card>
      )}
      <Card bodyClassName="p-0" title="Formula versions" actions={<Input placeholder="Filter…" value={q} onChange={(e) => setQ(e.target.value)} className="w-56" aria-label="Filter formulas" />}>
        {versions.error && <ErrorBanner error={versions.error} className="m-3" />}
        <DataTable columns={cols} rows={rows} rowKey={(v) => v.id} loading={versions.isLoading} onRowClick={(v) => navigate(`/metrics/${encodeURIComponent(v.metric_code)}`)} dense emptyTitle="No formula versions" />
      </Card>
    </div>
  );
}
