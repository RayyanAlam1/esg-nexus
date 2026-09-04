import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { issueAction, useIssues } from '@/api/governance';
import type { Issue, Severity } from '@/api/types';
import { useAuth } from '@/app/auth';
import { Card, DataTable, ErrorBanner, Field, Input, Modal, PageHeader, Select, SeverityBadge, StatCard, StatusBadge, Textarea, type Column } from '@/components/ui';
import { SEVERITY_ORDER } from '@/lib/colors';
import { fmtDateTime, titleCase } from '@/lib/format';
import { useDebounce } from '@/lib/utils';

const CATEGORIES = ['evidence_gap', 'data_missing', 'data_quality', 'inconsistency', 'framework_gap', 'governance', 'ai_quality', 'approval', 'target'];
type Action = 'acknowledge' | 'resolve' | 'exception';

export function IssuesPage() {
  const { hasCap } = useAuth();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const severity = params.get('severity') ?? '';
  const status = params.get('status') ?? 'open';
  const category = params.get('category') ?? '';
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounce(q, 300);
  const offset = Number(params.get('offset') ?? 0);
  const limit = 50;
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    if (k !== 'offset') p.delete('offset');
    setParams(p, { replace: true });
  };
  const list = useIssues({ severity: severity || undefined, status: status || undefined, category: category || undefined, limit, offset });
  const rows = (list.data?.items ?? []).filter((i) => !dq || `${i.code} ${i.title} ${i.metric_code ?? ''} ${i.entity_code ?? ''} ${i.rule_code ?? ''}`.toLowerCase().includes(dq.toLowerCase()));
  const [dialog, setDialog] = useState<{ issue: Issue; action: Action } | null>(null);
  const [comment, setComment] = useState('');
  const act = useMutation({
    mutationFn: () => issueAction((dialog as { issue: Issue }).issue.code, (dialog as { action: Action }).action, comment || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['governance'] });
      qc.invalidateQueries({ queryKey: ['esg'] });
      setDialog(null);
      setComment('');
    },
  });

  const cols: Column<Issue>[] = [
    { key: 'severity', header: 'Severity', render: (i) => <SeverityBadge severity={i.severity} /> },
    { key: 'code', header: 'Code', render: (i) => <span className="font-mono text-xs">{i.code}</span> },
    { key: 'title', header: 'Issue', render: (i) => <span><span className="font-medium">{i.title}</span>{i.description && <span className="block text-xs text-gray-500">{i.description}</span>}{i.required_action && <span className="block text-xs text-[#8F2C22]">Required: {i.required_action}</span>}</span> },
    { key: 'category', header: 'Category', render: (i) => titleCase(i.category) },
    { key: 'metric_code', header: 'Metric', render: (i) => (i.metric_code ? <Link to={`/metrics/${encodeURIComponent(i.metric_code)}`} className="font-mono text-xs text-teal">{i.metric_code}</Link> : '—') },
    { key: 'entity_code', header: 'Entity', render: (i) => i.entity_code ?? '—' },
    { key: 'period_code', header: 'Period', render: (i) => i.period_code ?? '—' },
    { key: 'rule_code', header: 'Rule', render: (i) => <span className="font-mono text-xs">{i.rule_code ?? '—'}</span> },
    { key: 'status', header: 'Status', render: (i) => <StatusBadge status={i.status} /> },
    { key: 'blocks_report', header: 'Blocks', render: (i) => (i.blocks_report ? <span className="text-[#8F2C22] font-medium">Yes</span> : 'No') },
    { key: 'created_at', header: 'Raised', render: (i) => fmtDateTime(i.created_at) },
    {
      key: 'actions',
      header: '',
      render: (i) =>
        i.status === 'open' || i.status === 'acknowledged' ? (
          <div className="flex gap-1">
            {i.status === 'open' && hasCap('metric.validate') && <button type="button" className="btn-secondary btn-sm" onClick={() => setDialog({ issue: i, action: 'acknowledge' })}>Acknowledge</button>}
            {hasCap('metric.approve') && <button type="button" className="btn-secondary btn-sm" onClick={() => setDialog({ issue: i, action: 'resolve' })}>Resolve</button>}
            {hasCap('governance.exception') && <button type="button" className="btn-danger btn-sm" onClick={() => setDialog({ issue: i, action: 'exception' })}>Exception</button>}
          </div>
        ) : (
          <span className="text-xs text-gray-500">{i.resolution_note ?? ''}</span>
        ),
    },
  ];

  const counts = list.data?.open_by_severity;
  return (
    <div className="space-y-4">
      <PageHeader title="Issues" description="Criticality engine output. Every open issue reduces report readiness; CRITICAL and blocking issues prevent publication until resolved or an exception is approved with a documented reason." showScope={false} />
      <div className="grid gap-2 grid-cols-5">
        {SEVERITY_ORDER.map((s: Severity) => (
          <StatCard key={s} label={s} value={counts?.[s] ?? '—'} onClick={() => set('severity', severity === s ? '' : s)} tone={severity === s ? 'text-teal' : undefined} hint={severity === s ? 'filtered' : 'open + acknowledged'} />
        ))}
      </div>
      <Card bodyClassName="p-3">
        <div className="grid gap-2 md:grid-cols-4">
          <Input placeholder="Search code, title, metric…" value={q} onChange={(e) => { setQ(e.target.value); set('q', e.target.value); }} aria-label="Search issues" />
          <Select value={status} onChange={(e) => set('status', e.target.value)} aria-label="Status"><option value="open">Open + acknowledged</option><option value="acknowledged">Acknowledged</option><option value="resolved">Resolved</option><option value="exception_approved">Exception approved</option><option value="all">All</option></Select>
          <Select value={severity} onChange={(e) => set('severity', e.target.value)} aria-label="Severity"><option value="">All severities</option>{SEVERITY_ORDER.map((s) => <option key={s} value={s}>{s}</option>)}</Select>
          <Select value={category} onChange={(e) => set('category', e.target.value)} aria-label="Category"><option value="">All categories</option>{CATEGORIES.map((c) => <option key={c} value={c}>{titleCase(c)}</option>)}</Select>
        </div>
      </Card>
      {list.error && <ErrorBanner error={list.error} />}
      <Card bodyClassName="p-0">
        <DataTable columns={cols} rows={rows} rowKey={(i) => i.id} loading={list.isLoading} pagination={{ total: list.data?.total ?? 0, limit, offset, onChange: (o) => set('offset', String(o)) }} dense emptyTitle="No issues" />
      </Card>
      <Modal open={!!dialog} onClose={() => setDialog(null)} title={dialog ? `${titleCase(dialog.action)} · ${dialog.issue.code}` : ''} footer={<><button type="button" className="btn-secondary" onClick={() => setDialog(null)}>Cancel</button><button type="button" className={dialog?.action === 'exception' ? 'btn-danger' : 'btn-primary'} onClick={() => act.mutate()} disabled={act.isPending || (dialog?.action === 'exception' && !comment.trim())}>Confirm</button></>}>
        {dialog && (
          <div className="space-y-3">
            {act.error ? <ErrorBanner error={act.error} /> : null}
            <div className="flex items-center gap-2"><SeverityBadge severity={dialog.issue.severity} /><span className="font-medium">{dialog.issue.title}</span></div>
            {dialog.issue.required_action && <p className="text-xs text-[#8F2C22]">Required action: {dialog.issue.required_action}</p>}
            {dialog.action === 'exception' && <p className="text-xs text-gray-700">An exception clears the report block for this issue and records an approval. A documented reason is mandatory and is written to the audit trail.</p>}
            <Field label={dialog.action === 'exception' ? 'Reason (required)' : 'Comment'} required={dialog.action === 'exception'}><Textarea value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
          </div>
        )}
      </Modal>
    </div>
  );
}
