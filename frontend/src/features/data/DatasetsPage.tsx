import { useState } from 'react';
import { Upload } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useDatasets, useSources } from '@/api/datasets';
import type { Dataset } from '@/api/types';
import { useAuth } from '@/app/auth';
import { Card, DataTable, ErrorBanner, PageHeader, Select, StatusBadge, type Column } from '@/components/ui';
import { PILLAR_LABEL } from '@/lib/colors';
import { fmtDateTime } from '@/lib/format';
import { UploadDialog } from './UploadDialog';

export function DatasetsPage() {
  const { hasCap } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const source = params.get('source') ?? '';
  const pillar = params.get('pillar') ?? '';
  const offset = Number(params.get('offset') ?? 0);
  const limit = 50;
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    if (k !== 'offset') p.delete('offset');
    setParams(p, { replace: true });
  };
  const sources = useSources();
  const q = useDatasets({ source: source || undefined, pillar: pillar || undefined, limit, offset });
  const [upload, setUpload] = useState(false);

  const cols: Column<Dataset>[] = [
    { key: 'code', header: 'Code', render: (d) => <span className="font-mono text-xs text-navy">{d.code}</span> },
    { key: 'name', header: 'Name', render: (d) => <span className="font-medium">{d.name}</span> },
    { key: 'source', header: 'Source', render: (d) => <span className="text-xs">{d.source_code} · {d.source_name}</span> },
    { key: 'pillar', header: 'Pillar', render: (d) => (d.pillar ? PILLAR_LABEL[d.pillar as keyof typeof PILLAR_LABEL] ?? d.pillar : '—') },
    { key: 'versions', header: 'Versions', align: 'right', render: (d) => d.version_count ?? 0 },
    { key: 'latest', header: 'Latest version', render: (d) => (d.latest_version ? <span className="text-xs">v{d.latest_version.version} · {d.latest_version.row_count} rows · {fmtDateTime(d.latest_version.uploaded_at)}</span> : '—') },
    { key: 'vstatus', header: 'Load status', render: (d) => <StatusBadge status={d.latest_version?.status ?? d.status} /> },
    { key: 'status', header: 'Dataset', render: (d) => <StatusBadge status={d.status} /> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Datasets"
        description="Ingested datasets with versions (raw → validated → normalised → loaded). Open a dataset to inspect versions, records and validation issues."
        showScope={false}
        actions={
          <>
            <Select value={source} onChange={(e) => set('source', e.target.value)} className="w-56" aria-label="Source filter">
              <option value="">All sources</option>
              {(sources.data ?? []).map((s) => (
                <option key={s.code} value={s.code}>{s.code} · {s.name}</option>
              ))}
            </Select>
            <Select value={pillar} onChange={(e) => set('pillar', e.target.value)} className="w-40" aria-label="Pillar filter">
              <option value="">All pillars</option>
              {Object.entries(PILLAR_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </Select>
            {hasCap('data.write') && (
              <button type="button" className="btn-primary" onClick={() => setUpload(true)}>
                <Upload size={14} /> Upload
              </button>
            )}
          </>
        }
      />
      {q.error && <ErrorBanner error={q.error} />}
      <Card bodyClassName="p-0">
        <DataTable columns={cols} rows={q.data?.items} rowKey={(d) => d.id} loading={q.isLoading} onRowClick={(d) => navigate(`/data/datasets/${d.id}`)} pagination={{ total: q.data?.total ?? 0, limit, offset, onChange: (o) => set('offset', String(o)) }} emptyTitle="No datasets" dense />
      </Card>
      <UploadDialog open={upload} onClose={() => setUpload(false)} />
    </div>
  );
}
