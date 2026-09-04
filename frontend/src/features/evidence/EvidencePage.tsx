import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { createEvidence, useEvidenceKinds, useEvidenceList, type EvidenceIn } from '@/api/evidence';
import type { EvidenceItem } from '@/api/types';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { Card, DataTable, Drawer, ErrorBanner, Field, Input, PageHeader, Select, StatusBadge, Textarea, type Column } from '@/components/ui';
import { fmtDate, titleCase } from '@/lib/format';
import { useDebounce } from '@/lib/utils';

export function EvidencePage() {
  const { hasCap } = useAuth();
  const { period, entity } = useAppContext();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounce(q, 300);
  const kind = params.get('kind') ?? '';
  const status = params.get('status') ?? '';
  const metric = params.get('metric') ?? '';
  const offset = Number(params.get('offset') ?? 0);
  const limit = 50;
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    if (k !== 'offset') p.delete('offset');
    setParams(p, { replace: true });
  };
  const kinds = useEvidenceKinds();
  const list = useEvidenceList({ kind: kind || undefined, status: status || undefined, q: dq || undefined, metric: metric || undefined, limit, offset });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<EvidenceIn>({ code: '', title: '', kind: 'report_page', source: '', document_ref: '', printed_page: '', excerpt: '', entity_code: entity, period_code: period, metric_codes: [] });
  const [metricCodes, setMetricCodes] = useState('');
  const create = useMutation({
    mutationFn: () => createEvidence({ ...form, metric_codes: metricCodes.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean), page_from: form.page_from ?? null, page_to: form.page_to ?? null }),
    onSuccess: (ev) => {
      qc.invalidateQueries({ queryKey: ['evidence'] });
      setOpen(false);
      navigate(`/evidence/${encodeURIComponent(ev.code)}`);
    },
  });

  const cols: Column<EvidenceItem>[] = [
    { key: 'code', header: 'Code', sortable: true, render: (e) => <span className="font-mono text-xs text-navy">{e.code}</span> },
    { key: 'title', header: 'Title', sortable: true, render: (e) => <span className="font-medium">{e.title}</span> },
    { key: 'kind', header: 'Kind', sortable: true, render: (e) => titleCase(e.kind) },
    { key: 'document_ref', header: 'Document', render: (e) => <span className="text-xs">{e.document_ref ?? '—'}{e.printed_page ? ` · p. ${e.printed_page}` : ''}</span> },
    { key: 'excerpt', header: 'Excerpt', render: (e) => <span className="text-xs text-gray-600 line-clamp-2">{e.excerpt || '—'}</span> },
    { key: 'evidence_date', header: 'Date', sortable: true, render: (e) => fmtDate(e.evidence_date) },
    { key: 'link_count', header: 'Links', align: 'right', render: (e) => e.link_count ?? 0 },
    { key: 'verification_status', header: 'Verification', sortable: true, render: (e) => <StatusBadge status={e.verification_status} /> },
  ];

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Evidence Repository"
        description="Every document, page reference, record and extract used to support reported values. Evidence carries a hash, page references, verification status and links to metrics."
        showScope={false}
        actions={hasCap('evidence.write') && <button type="button" className="btn-primary" onClick={() => setOpen(true)}><Plus size={14} /> Register evidence</button>}
      />
      <Card bodyClassName="p-3">
        <div className="grid gap-2 md:grid-cols-4">
          <Input placeholder="Search title, code, excerpt…" value={q} onChange={(e) => { setQ(e.target.value); set('q', e.target.value); }} aria-label="Search evidence" />
          <Select value={kind} onChange={(e) => set('kind', e.target.value)} aria-label="Kind">
            <option value="">All kinds</option>
            {(kinds.data ?? []).map((k) => <option key={k} value={k}>{titleCase(k)}</option>)}
          </Select>
          <Select value={status} onChange={(e) => set('status', e.target.value)} aria-label="Verification status">
            <option value="">All statuses</option>
            {['unverified', 'verified', 'rejected'].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
          </Select>
          <Input placeholder="Metric code filter" value={metric} onChange={(e) => set('metric', e.target.value.trim())} aria-label="Metric filter" />
        </div>
      </Card>
      {list.error && <ErrorBanner error={list.error} />}
      <Card bodyClassName="p-0">
        <DataTable
          columns={cols}
          rows={list.data?.items}
          rowKey={(e) => e.id}
          loading={list.isLoading}
          onRowClick={(e) => navigate(`/evidence/${encodeURIComponent(e.code)}`)}
          pagination={{ total: list.data?.total ?? 0, limit, offset, onChange: (o) => set('offset', String(o)) }}
          sort={{ sort: params.get('sort') ?? undefined, order: (params.get('order') as 'asc' | 'desc') ?? undefined, onChange: (s, o) => { set('sort', s); set('order', o); } }}
          dense
          emptyTitle="No evidence matches"
        />
      </Card>
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="Register evidence"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Cancel</button>
            <button type="submit" form="evidence-form" className="btn-primary" disabled={create.isPending || !form.code || !form.title}>Create</button>
          </>
        }
      >
        <form id="evidence-form" onSubmit={submit} className="space-y-3">
          {create.error ? <ErrorBanner error={create.error} /> : null}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Code" required><Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.trim() })} placeholder="EV-2023-P120" required /></Field>
            <Field label="Kind"><Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{(kinds.data ?? ['report_page']).map((k) => <option key={k} value={k}>{titleCase(k)}</option>)}</Select></Field>
          </div>
          <Field label="Title" required><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Source"><Input value={form.source ?? ''} onChange={(e) => setForm({ ...form, source: e.target.value })} /></Field>
            <Field label="Document reference"><Input value={form.document_ref ?? ''} onChange={(e) => setForm({ ...form, document_ref: e.target.value })} /></Field>
            <Field label="Printed page"><Input value={form.printed_page ?? ''} onChange={(e) => setForm({ ...form, printed_page: e.target.value })} /></Field>
            <Field label="PDF page from / to">
              <div className="flex gap-2">
                <Input type="number" value={form.page_from ?? ''} onChange={(e) => setForm({ ...form, page_from: e.target.value === '' ? null : Number(e.target.value) })} />
                <Input type="number" value={form.page_to ?? ''} onChange={(e) => setForm({ ...form, page_to: e.target.value === '' ? null : Number(e.target.value) })} />
              </div>
            </Field>
            <Field label="Entity"><Input value={form.entity_code ?? ''} onChange={(e) => setForm({ ...form, entity_code: e.target.value })} /></Field>
            <Field label="Period"><Input value={form.period_code ?? ''} onChange={(e) => setForm({ ...form, period_code: e.target.value })} /></Field>
            <Field label="Evidence date"><Input type="date" value={form.evidence_date ?? ''} onChange={(e) => setForm({ ...form, evidence_date: e.target.value || null })} /></Field>
            <Field label="Confidence (0–1)"><Input type="number" min={0} max={1} step="0.05" value={form.confidence ?? ''} onChange={(e) => setForm({ ...form, confidence: e.target.value === '' ? null : Number(e.target.value) })} /></Field>
          </div>
          <Field label="Excerpt"><Textarea value={form.excerpt ?? ''} onChange={(e) => setForm({ ...form, excerpt: e.target.value })} /></Field>
          <Field label="Link to metrics" hint="Comma separated metric codes"><Input value={metricCodes} onChange={(e) => setMetricCodes(e.target.value)} placeholder="ENV.GHG.SCOPE1, ENV.GHG.SCOPE2" /></Field>
        </form>
      </Drawer>
    </div>
  );
}
