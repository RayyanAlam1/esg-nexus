import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { loadVersion, useDataset, useRecords } from '@/api/datasets';
import type { DatasetRecord, DatasetVersion } from '@/api/types';
import { useAuth } from '@/app/auth';
import { Card, DataTable, EmptyState, ErrorBanner, JsonDetails, JsonViewer, LoadingBlock, PageHeader, StatCard, StatusBadge, type Column } from '@/components/ui';
import { fmtDateTime, fmtNumber } from '@/lib/format';
import { cn } from '@/lib/utils';

export function DatasetDetailPage() {
  const { id } = useParams();
  const { hasCap } = useAuth();
  const qc = useQueryClient();
  const q = useDataset(id ? Number(id) : null);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [onlyInvalid, setOnlyInvalid] = useState(false);
  const [offset, setOffset] = useState(0);
  const limit = 50;
  useEffect(() => {
    if (q.data?.versions.length && versionId === null) setVersionId(q.data.versions[q.data.versions.length - 1].id);
  }, [q.data, versionId]);
  const records = useRecords(versionId, { only_invalid: onlyInvalid, limit, offset });
  const load = useMutation({
    mutationFn: (vid: number) => loadVersion(vid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['datasets'] });
      qc.invalidateQueries({ queryKey: ['metrics'] });
    },
  });

  if (q.isLoading) return <LoadingBlock lines={8} />;
  if (q.error) return <ErrorBanner error={q.error} />;
  const d = q.data;
  if (!d) return <EmptyState />;
  const v = d.versions.find((x) => x.id === versionId) ?? null;

  const vcols: Column<DatasetVersion>[] = [
    { key: 'version', header: 'v', render: (x) => `v${x.version}` },
    { key: 'file_name', header: 'File', render: (x) => <span className="text-xs">{x.file_name ?? '—'}</span> },
    { key: 'row_count', header: 'Rows', align: 'right' },
    { key: 'status', header: 'Status', render: (x) => <StatusBadge status={x.status} /> },
    { key: 'uploaded_at', header: 'Uploaded', render: (x) => fmtDateTime(x.uploaded_at) },
    { key: 'file_hash', header: 'SHA-256', render: (x) => <span className="font-mono text-xxs text-gray-500">{x.file_hash?.slice(0, 16) ?? '—'}…</span> },
  ];
  const rcols: Column<DatasetRecord>[] = [
    { key: 'row_index', header: '#', align: 'right' },
    { key: 'is_valid', header: 'Valid', render: (r) => <StatusBadge status={r.is_valid ? 'ok' : 'error'} label={r.is_valid ? 'Valid' : 'Invalid'} /> },
    { key: 'metric_code', header: 'Metric', render: (r) => (r.metric_code ? <Link to={`/metrics/${encodeURIComponent(r.metric_code)}`} className="font-mono text-xs text-teal">{r.metric_code}</Link> : <span className="text-gray-400">unmapped</span>) },
    { key: 'entity_code', header: 'Entity', render: (r) => r.entity_code ?? '—' },
    { key: 'period_code', header: 'Period', render: (r) => r.period_code ?? '—' },
    { key: 'value', header: 'Value', align: 'right', render: (r) => (r.value !== null ? fmtNumber(r.value) : r.value_text ?? '—') },
    { key: 'unit', header: 'Unit', render: (r) => r.unit ?? '' },
    { key: 'mapping_confidence', header: 'Map conf.', align: 'right', render: (r) => (r.mapping_confidence !== null ? fmtNumber(r.mapping_confidence, { decimals: 2 }) : '—') },
    { key: 'issues', header: 'Issues', render: (r) => (r.issues?.length ? <ul className="text-xs text-[#8F2C22] list-disc pl-4">{r.issues.map((i, k) => <li key={k}>{typeof i === 'string' ? i : JSON.stringify(i)}</li>)}</ul> : '—') },
    { key: 'payload', header: 'Raw', render: (r) => <JsonDetails label="row" value={r.payload} /> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title={<span>{d.name} <span className="font-mono text-sm text-gray-500 font-normal">{d.code}</span></span>} description={d.description ?? undefined} showScope={false} actions={<StatusBadge status={d.status} />} />
      <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
        <StatCard label="Source" value={<span className="text-sm">{d.source.name}</span>} hint={`${d.source.code} · ${d.source.kind}${d.source.system_name ? ` · ${d.source.system_name}` : ''}`} />
        <StatCard label="Versions" value={d.versions.length} />
        <StatCard label="Latest rows" value={fmtNumber(d.versions[d.versions.length - 1]?.row_count ?? null)} />
        <StatCard label="Pillar" value={<span className="text-sm">{d.pillar ?? '—'}</span>} />
      </div>
      <Card title="Versions" bodyClassName="p-0">
        <DataTable columns={vcols} rows={d.versions} rowKey={(x) => x.id} onRowClick={(x) => { setVersionId(x.id); setOffset(0); }} rowClassName={(x) => (x.id === versionId ? 'bg-navy-50' : undefined)} dense emptyTitle="No versions" />
      </Card>
      {v && (
        <>
          <div className="grid gap-3 lg:grid-cols-3">
            <Card title={`Validation · v${v.version}`}>
              <JsonViewer value={v.validation_result} maxHeight={200} />
            </Card>
            <Card title="Quality">
              <JsonViewer value={v.quality} maxHeight={200} />
            </Card>
            <Card title="Transformation history" actions={hasCap('data.write') && v.status !== 'loaded' ? <button type="button" className="btn-secondary btn-sm" onClick={() => load.mutate(v.id)} disabled={load.isPending}>Load values</button> : null}>
              {load.error ? <ErrorBanner error={load.error} /> : null}
              {load.data ? <p className="text-xs text-[#1F7A3A] mb-2">Loaded {load.data.loaded_values} values · status {load.data.status}</p> : null}
              <ol className="text-xs space-y-1 list-decimal pl-4">
                {(v.transformation_history ?? []).map((h, i) => (
                  <li key={i}><span className="font-medium">{h.step}</span> <span className="text-gray-500">{fmtDateTime(h.at)}</span>{Object.entries(h).filter(([k]) => !['step', 'at'].includes(k)).map(([k, val]) => <span key={k} className="text-gray-600"> · {k}: {String(val)}</span>)}</li>
                ))}
              </ol>
            </Card>
          </div>
          <Card
            title={`Records · v${v.version}`}
            bodyClassName="p-0"
            actions={
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={onlyInvalid} onChange={(e) => { setOnlyInvalid(e.target.checked); setOffset(0); }} /> Invalid rows only
              </label>
            }
          >
            {records.error && <ErrorBanner error={records.error} className="m-3" />}
            <DataTable columns={rcols} rows={records.data?.items} rowKey={(r) => r.id} loading={records.isLoading} pagination={{ total: records.data?.total ?? 0, limit, offset, onChange: setOffset }} rowClassName={(r) => cn(!r.is_valid && 'bg-red-50/40')} dense emptyTitle="No records" />
          </Card>
        </>
      )}
    </div>
  );
}
