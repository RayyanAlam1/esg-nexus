import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { createTarget, useTargets, type TargetIn } from '@/api/metrics';
import type { TargetRow } from '@/api/types';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { Card, DataTable, Drawer, ErrorBanner, Field, Input, PageHeader, ProgressBar, Select, StatusBadge, Textarea, type Column } from '@/components/ui';
import { scoreHex } from '@/lib/colors';
import { fmtNumber } from '@/lib/format';

export function TargetsPage() {
  const { hasCap } = useAuth();
  const { entities, entity } = useAppContext();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [status, setStatus] = useState('');
  const targets = useTargets(status || undefined);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<TargetIn>({ metric_code: '', entity_code: entity, direction: 'decrease', kind: 'absolute', status: 'active', target_year: 2030 });
  const create = useMutation({
    mutationFn: () => createTarget({ ...form, entity_code: form.entity_code || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['targets'] });
      setOpen(false);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  const cols: Column<TargetRow>[] = [
    { key: 'metric_code', header: 'Metric', render: (t) => <span className="font-mono text-xs text-navy">{t.metric_code}</span> },
    { key: 'metric_name', header: 'Name', render: (t) => <span className="font-medium">{t.metric_name}</span> },
    { key: 'entity_code', header: 'Entity' },
    { key: 'baseline_value', header: 'Baseline', align: 'right', render: (t) => fmtNumber(t.baseline_value) },
    { key: 'current_value', header: `Current`, align: 'right', render: (t) => (t.current_value === null ? <span className="text-gray-400 italic">Data unavailable</span> : `${fmtNumber(t.current_value)} (${t.current_period})`) },
    { key: 'target_value', header: 'Target', align: 'right', render: (t) => `${fmtNumber(t.target_value)}${t.unit ? ` ${t.unit}` : ''}${t.target_year ? ` by ${t.target_year}` : ''}` },
    { key: 'direction', header: 'Direction', render: (t) => t.direction },
    {
      key: 'progress_pct',
      header: 'Progress',
      width: '180px',
      render: (t) =>
        t.progress_pct === null ? (
          <span className="text-xs text-gray-400">Not measurable (missing baseline or value)</span>
        ) : (
          <div className="flex items-center gap-2">
            <ProgressBar value={Math.max(0, Math.min(100, t.progress_pct))} color={scoreHex(t.progress_pct)} className="flex-1" />
            <span className="text-xs tabular-nums w-12 text-right">{fmtNumber(t.progress_pct, { decimals: 1 })}%</span>
          </div>
        ),
    },
    { key: 'status', header: 'Status', render: (t) => <StatusBadge status={t.status} /> },
    { key: 'description', header: 'Description', render: (t) => <span className="text-xs text-gray-600">{t.description ?? '—'}</span> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Targets"
        description="Targets with baseline, current value and progress. Progress = (current − baseline) / (target − baseline)."
        showScope={false}
        actions={
          <>
            <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-40" aria-label="Status filter">
              <option value="">All statuses</option>
              {['active', 'achieved', 'missed', 'not_set'].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </Select>
            {hasCap('metric.write') && (
              <button type="button" className="btn-primary" onClick={() => setOpen(true)}>
                <Plus size={14} /> New target
              </button>
            )}
          </>
        }
      />
      {targets.error && <ErrorBanner error={targets.error} />}
      <Card bodyClassName="p-0">
        <DataTable columns={cols} rows={targets.data} rowKey={(t) => t.id} loading={targets.isLoading} onRowClick={(t) => navigate(`/metrics/${encodeURIComponent(t.metric_code)}`)} dense emptyTitle="No targets" />
      </Card>
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="Create target"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Cancel</button>
            <button type="submit" form="target-form" className="btn-primary" disabled={create.isPending || !form.metric_code}>Create</button>
          </>
        }
      >
        <form id="target-form" onSubmit={submit} className="space-y-3">
          {create.error ? <ErrorBanner error={create.error} /> : null}
          <Field label="Metric code" required>
            <Input value={form.metric_code} onChange={(e) => setForm({ ...form, metric_code: e.target.value.trim() })} placeholder="ENV.GHG.SCOPE1_2_TOTAL" required />
          </Field>
          <Field label="Entity">
            <Select value={form.entity_code ?? ''} onChange={(e) => setForm({ ...form, entity_code: e.target.value })}>
              {entities.map((e) => (
                <option key={e.code} value={e.code}>{e.code} · {e.name}</option>
              ))}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Baseline value">
              <Input type="number" step="any" value={form.baseline_value ?? ''} onChange={(e) => setForm({ ...form, baseline_value: e.target.value === '' ? null : Number(e.target.value) })} />
            </Field>
            <Field label="Target value">
              <Input type="number" step="any" value={form.target_value ?? ''} onChange={(e) => setForm({ ...form, target_value: e.target.value === '' ? null : Number(e.target.value) })} />
            </Field>
            <Field label="Target year">
              <Input type="number" value={form.target_year ?? ''} onChange={(e) => setForm({ ...form, target_year: e.target.value === '' ? null : Number(e.target.value) })} />
            </Field>
            <Field label="Direction">
              <Select value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })}>
                {['decrease', 'increase', 'maintain', 'achieve'].map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </Select>
            </Field>
            <Field label="Kind">
              <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {['absolute', 'relative_pct', 'intensity', 'qualitative'].map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </Select>
            </Field>
            <Field label="Status">
              <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {['active', 'achieved', 'missed', 'not_set'].map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Description">
            <Textarea value={form.description ?? ''} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
        </form>
      </Drawer>
    </div>
  );
}
