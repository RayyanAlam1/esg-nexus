import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { decideApproval, useApprovals } from '@/api/governance';
import type { Approval } from '@/api/types';
import { useAuth } from '@/app/auth';
import { Card, DataTable, ErrorBanner, Field, JsonDetails, Modal, PageHeader, Select, StatusBadge, Tabs, Textarea, type Column } from '@/components/ui';
import { fmtDateTime, titleCase } from '@/lib/format';

export function ApprovalsPage() {
  const { hasCap } = useAuth();
  const qc = useQueryClient();
  const [tab, setTab] = useState<'pending' | 'all'>('pending');
  const q = useApprovals(tab === 'pending');
  const [target, setTarget] = useState<Approval | null>(null);
  const [decision, setDecision] = useState('approved');
  const [comment, setComment] = useState('');
  const decide = useMutation({
    mutationFn: () => decideApproval((target as Approval).id, decision, comment || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['governance'] });
      setTarget(null);
      setComment('');
    },
  });
  const objectLink = (a: Approval) => {
    if (a.object_type === 'report') return `/reports/${a.object_id}/preview`;
    if (a.object_type === 'exception') return `/governance/issues?status=all&q=${encodeURIComponent(a.object_id)}`;
    if (a.object_type === 'metric_value') return `/metrics/${encodeURIComponent(a.object_id.split('/')[0])}`;
    return null;
  };
  const cols: Column<Approval>[] = [
    { key: 'id', header: '#', align: 'right' },
    { key: 'object_type', header: 'Object', render: (a) => titleCase(a.object_type) },
    { key: 'object_id', header: 'Reference', render: (a) => { const l = objectLink(a); return l ? <Link to={l} className="font-mono text-xs text-teal">{a.object_id}</Link> : <span className="font-mono text-xs">{a.object_id}</span>; } },
    { key: 'state', header: 'State', render: (a) => <StatusBadge status={a.state} /> },
    { key: 'requested_by_email', header: 'Requested by', render: (a) => a.requested_by_email ?? a.requested_by ?? '—' },
    { key: 'created_at', header: 'Requested', render: (a) => fmtDateTime(a.created_at) },
    { key: 'decision', header: 'Decision', render: (a) => (a.decision ? <StatusBadge status={a.decision} /> : <span className="text-gray-400">pending</span>) },
    { key: 'decided_at', header: 'Decided', render: (a) => fmtDateTime(a.decided_at) },
    { key: 'comment', header: 'Comment', render: (a) => <span className="text-xs text-gray-600">{a.comment ?? '—'}</span> },
    { key: 'context', header: 'Context', render: (a) => (a.context ? <JsonDetails label="context" value={a.context} /> : '—') },
    { key: 'actions', header: '', render: (a) => (!a.decision && hasCap('review') ? <button type="button" className="btn-primary btn-sm" onClick={() => setTarget(a)}>Decide</button> : null) },
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Approvals" description="Human-in-the-loop decisions on reports, sections, exceptions, AI outputs and mappings. Reports and exceptions require an approver role." showScope={false} />
      <Tabs tabs={[{ key: 'pending', label: 'Pending' }, { key: 'all', label: 'All' }]} active={tab} onChange={(k) => setTab(k as 'pending' | 'all')} />
      {q.error && <ErrorBanner error={q.error} />}
      <Card bodyClassName="p-0"><DataTable columns={cols} rows={q.data} rowKey={(a) => a.id} loading={q.isLoading} dense emptyTitle={tab === 'pending' ? 'No pending approvals' : 'No approvals'} /></Card>
      <Modal open={!!target} onClose={() => setTarget(null)} title={target ? `Decide · ${titleCase(target.object_type)} ${target.object_id}` : ''} footer={<><button type="button" className="btn-secondary" onClick={() => setTarget(null)}>Cancel</button><button type="button" className="btn-primary" onClick={() => decide.mutate()} disabled={decide.isPending}>Submit decision</button></>}>
        <div className="space-y-3">
          {decide.error ? <ErrorBanner error={decide.error} /> : null}
          <Field label="Decision"><Select value={decision} onChange={(e) => setDecision(e.target.value)}>{['approved', 'rejected', 'changes_requested'].map((d) => <option key={d} value={d}>{titleCase(d)}</option>)}</Select></Field>
          <Field label="Comment"><Textarea value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
        </div>
      </Modal>
    </div>
  );
}
