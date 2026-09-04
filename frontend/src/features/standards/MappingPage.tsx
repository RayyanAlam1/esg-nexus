import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { createMapping, useMappings, type MappingIn } from '@/api/frameworks';
import type { FrameworkMapping } from '@/api/types';
import { useAuth } from '@/app/auth';
import { Card, DataTable, Drawer, ErrorBanner, Field, Input, PageHeader, Select, StatusBadge, Textarea, type Column } from '@/components/ui';
import { fmtDate, fmtNumber } from '@/lib/format';

export function MappingPage() {
  const { hasCap } = useAuth();
  const qc = useQueryClient();
  const q = useMappings();
  const [filter, setFilter] = useState('');
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<MappingIn>({ requirement_code: '', metric_code: '', mapping_type: 'direct', rationale: '', omission_reason: '', confidence: null });
  const create = useMutation({
    mutationFn: () => createMapping({ ...form, metric_code: form.metric_code || null, omission_reason: form.mapping_type === 'omitted' ? form.omission_reason : null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['frameworks'] });
      setOpen(false);
    },
  });
  const rows = (q.data ?? []).filter((m) => !filter || `${m.requirement_code} ${m.requirement_title} ${m.metric_code ?? ''}`.toLowerCase().includes(filter.toLowerCase()));

  const cols: Column<FrameworkMapping>[] = [
    { key: 'requirement_code', header: 'Requirement', render: (m) => <span className="font-mono text-xs text-navy">{m.requirement_code}</span> },
    { key: 'requirement_title', header: 'Title', render: (m) => m.requirement_title },
    { key: 'metric_code', header: 'Metric', render: (m) => (m.metric_code ? <Link to={`/metrics/${encodeURIComponent(m.metric_code)}`} className="font-mono text-xs text-teal">{m.metric_code}</Link> : <span className="text-gray-400">— (narrative / omitted)</span>) },
    { key: 'mapping_type', header: 'Type', render: (m) => <StatusBadge status={m.mapping_type} /> },
    { key: 'status', header: 'Status', render: (m) => <StatusBadge status={m.status} /> },
    { key: 'confidence', header: 'Confidence', align: 'right', render: (m) => (m.confidence === null ? '—' : fmtNumber(m.confidence, { decimals: 2 })) },
    { key: 'rationale', header: 'Rationale', render: (m) => <span className="text-xs text-gray-600">{m.rationale ?? m.omission_reason ?? '—'}</span> },
    { key: 'created_at', header: 'Created', render: (m) => fmtDate(m.created_at) },
  ];

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Framework Mapping"
        description="Tenant-specific mappings between framework requirements and metrics (direct, partial, derived, narrative) or documented omissions."
        showScope={false}
        actions={
          <>
            <Input placeholder="Filter…" value={filter} onChange={(e) => setFilter(e.target.value)} className="w-56" aria-label="Filter mappings" />
            {hasCap('framework.manage') && (
              <button type="button" className="btn-primary" onClick={() => setOpen(true)}>
                <Plus size={14} /> New mapping
              </button>
            )}
          </>
        }
      />
      {q.error && <ErrorBanner error={q.error} />}
      <Card bodyClassName="p-0">
        <DataTable columns={cols} rows={rows} rowKey={(m) => m.id} loading={q.isLoading} dense emptyTitle="No custom mappings" emptyHint="Default requirement → metric mappings come from the framework YAML; custom mappings and omissions are recorded here." />
      </Card>
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="Create mapping"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Cancel</button>
            <button type="submit" form="mapping-form" className="btn-primary" disabled={create.isPending || !form.requirement_code}>Create</button>
          </>
        }
      >
        <form id="mapping-form" onSubmit={submit} className="space-y-3">
          {create.error ? <ErrorBanner error={create.error} /> : null}
          <Field label="Requirement code" required>
            <Input value={form.requirement_code} onChange={(e) => setForm({ ...form, requirement_code: e.target.value.trim() })} placeholder="WEF.PLANET.GHG_EMISSIONS" required />
          </Field>
          <Field label="Mapping type">
            <Select value={form.mapping_type} onChange={(e) => setForm({ ...form, mapping_type: e.target.value })}>
              {['direct', 'partial', 'derived', 'narrative', 'omitted'].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </Select>
          </Field>
          {form.mapping_type !== 'omitted' && (
            <Field label="Metric code" hint="Leave blank for narrative-only mapping">
              <Input value={form.metric_code ?? ''} onChange={(e) => setForm({ ...form, metric_code: e.target.value.trim() })} placeholder="ENV.GHG.SCOPE1" />
            </Field>
          )}
          {form.mapping_type === 'omitted' && (
            <Field label="Omission reason" required>
              <Textarea value={form.omission_reason ?? ''} onChange={(e) => setForm({ ...form, omission_reason: e.target.value })} required />
            </Field>
          )}
          <Field label="Rationale">
            <Textarea value={form.rationale ?? ''} onChange={(e) => setForm({ ...form, rationale: e.target.value })} />
          </Field>
          <Field label="Confidence (0–1)">
            <Input type="number" min={0} max={1} step="0.05" value={form.confidence ?? ''} onChange={(e) => setForm({ ...form, confidence: e.target.value === '' ? null : Number(e.target.value) })} />
          </Field>
        </form>
      </Drawer>
    </div>
  );
}
