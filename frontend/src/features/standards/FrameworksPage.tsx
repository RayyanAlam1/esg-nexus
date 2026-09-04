import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { selectFrameworks, useFrameworks, useSelectedFrameworks } from '@/api/frameworks';
import type { Framework } from '@/api/types';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { Card, DataTable, ErrorBanner, PageHeader, StatusBadge, type Column } from '@/components/ui';
import { fmtDate } from '@/lib/format';

export function FrameworksPage() {
  const { period } = useAppContext();
  const { hasCap } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const fws = useFrameworks();
  const selected = useSelectedFrameworks(period);
  const selectedCodes = new Set((selected.data?.frameworks ?? []).map((f) => f.framework_code));
  const select = useMutation({ mutationFn: (code: string) => selectFrameworks([code], period), onSuccess: () => qc.invalidateQueries({ queryKey: ['frameworks', 'selected'] }) });

  const cols: Column<Framework>[] = [
    { key: 'code', header: 'Code', render: (f) => <span className="font-mono text-xs text-navy">{f.code}</span> },
    { key: 'name', header: 'Framework', render: (f) => <span className="font-medium">{f.name}</span> },
    { key: 'publisher', header: 'Publisher', render: (f) => f.publisher ?? '—' },
    { key: 'current_version', header: 'Version', render: (f) => f.current_version ?? '—' },
    { key: 'effective_date', header: 'Effective', render: (f) => fmtDate(f.effective_date) },
    { key: 'requirement_count', header: 'Requirements', align: 'right' },
    { key: 'jurisdiction', header: 'Jurisdiction', render: (f) => f.jurisdiction ?? 'Global' },
    { key: 'selected', header: `Selected · ${period}`, render: (f) => (selectedCodes.has(f.code) ? <StatusBadge status="active" label="Selected" /> : hasCap('framework.manage') ? <button type="button" className="btn-secondary btn-sm" onClick={(e) => { e.stopPropagation(); select.mutate(f.code); }} disabled={select.isPending}>Select</button> : <span className="text-gray-400">—</span>) },
    { key: 'actions', header: '', render: (f) => <button type="button" className="text-xs text-teal" onClick={(e) => { e.stopPropagation(); navigate(`/standards/compliance?framework=${f.code}`); }}>Alignment</button> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title="Frameworks" description="Configuration-driven registry of reporting frameworks and standards. Click a framework to browse its requirements; select frameworks per reporting period." />
      {fws.error && <ErrorBanner error={fws.error} />}
      {select.error ? <ErrorBanner error={select.error} /> : null}
      <Card bodyClassName="p-0">
        <DataTable columns={cols} rows={fws.data} rowKey={(f) => f.code} loading={fws.isLoading} onRowClick={(f) => navigate(`/standards/frameworks/${f.code}`)} dense emptyTitle="No frameworks loaded" />
      </Card>
    </div>
  );
}
