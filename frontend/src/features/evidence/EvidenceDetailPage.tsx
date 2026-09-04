import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { linkEvidence, useEvidence, verifyEvidence } from '@/api/evidence';
import type { EvidenceLinkRow } from '@/api/types';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { Card, DataTable, EmptyState, ErrorBanner, Field, Input, JsonViewer, LoadingBlock, Modal, PageHeader, Select, StatusBadge, Textarea, type Column } from '@/components/ui';
import { fmtDate, fmtDateTime, fmtNumber, titleCase } from '@/lib/format';

export function EvidenceDetailPage() {
  const { code } = useParams();
  const { hasCap } = useAuth();
  const { period, entity } = useAppContext();
  const qc = useQueryClient();
  const q = useEvidence(code);
  const [link, setLink] = useState(false);
  const [verify, setVerify] = useState(false);
  const [linkForm, setLinkForm] = useState({ metric_code: '', entity_code: entity, period_code: period, relation: 'supports', note: '' });
  const [verifyForm, setVerifyForm] = useState({ status: 'verified', comment: '', confidence: '' });
  const invalidate = () => qc.invalidateQueries({ queryKey: ['evidence'] });
  const doLink = useMutation({ mutationFn: () => linkEvidence(code as string, { ...linkForm, entity_code: linkForm.entity_code || null, period_code: linkForm.period_code || null }), onSuccess: () => { invalidate(); setLink(false); } });
  const doVerify = useMutation({ mutationFn: () => verifyEvidence(code as string, { status: verifyForm.status, comment: verifyForm.comment || null, confidence: verifyForm.confidence === '' ? null : Number(verifyForm.confidence) }), onSuccess: () => { invalidate(); setVerify(false); } });

  if (q.isLoading) return <LoadingBlock lines={8} />;
  if (q.error) return <ErrorBanner error={q.error} />;
  const e = q.data;
  if (!e) return <EmptyState />;

  const cols: Column<EvidenceLinkRow>[] = [
    { key: 'metric_code', header: 'Metric', render: (l) => (l.metric_code ? <Link to={`/metrics/${encodeURIComponent(l.metric_code)}`} className="font-mono text-xs text-teal">{l.metric_code}</Link> : '—') },
    { key: 'metric_name', header: 'Name', render: (l) => l.metric_name ?? '—' },
    { key: 'entity', header: 'Entity', render: (l) => l.entity ?? <span className="text-gray-400">definition-level</span> },
    { key: 'period', header: 'Period', render: (l) => l.period ?? '—' },
    { key: 'value', header: 'Value', align: 'right', render: (l) => fmtNumber(l.value) },
    { key: 'relation', header: 'Relation', render: (l) => <StatusBadge status={l.relation === 'contradicts' ? 'rejected' : 'active'} label={l.relation} /> },
    { key: 'requirement_id', header: 'Requirement', render: (l) => l.requirement_id ?? '—' },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title={<span>{e.title} <span className="font-mono text-sm text-gray-500 font-normal">{e.code}</span></span>}
        description={`${titleCase(e.kind)}${e.source ? ` · ${e.source}` : ''}`}
        showScope={false}
        actions={
          <>
            <StatusBadge status={e.verification_status} />
            {hasCap('evidence.write') && <button type="button" className="btn-secondary" onClick={() => setLink(true)}>Link to metric</button>}
            {hasCap('evidence.verify') && <button type="button" className="btn-primary" onClick={() => setVerify(true)}>Verify</button>}
          </>
        }
      />
      <div className="grid gap-3 lg:grid-cols-2">
        <Card title="Metadata">
          <dl className="kv">
            <dt>Document</dt><dd>{e.document_ref ?? '—'}</dd>
            <dt>Pages</dt><dd>{e.printed_page ? `printed p. ${e.printed_page}` : ''}{e.page_from ? ` · pdf ${e.page_from}${e.page_to && e.page_to !== e.page_from ? `–${e.page_to}` : ''}` : ''}{!e.printed_page && !e.page_from ? '—' : ''}</dd>
            <dt>Evidence date</dt><dd>{fmtDate(e.evidence_date)}</dd>
            <dt>Version</dt><dd>{e.version}</dd>
            <dt>Confidence</dt><dd>{e.confidence === null ? '—' : fmtNumber(e.confidence, { decimals: 2 })}</dd>
            <dt>SHA-256</dt><dd className="font-mono text-xxs break-all">{e.file_hash ?? '—'}</dd>
            <dt>Storage key</dt><dd className="font-mono text-xxs break-all">{e.storage_key ?? '—'}</dd>
            <dt>Owner</dt><dd>{e.owner_id ?? '—'}</dd>
            <dt>Verified by</dt><dd>{e.verified_by ?? '—'}</dd>
            <dt>Registered</dt><dd>{fmtDateTime(e.created_at)}</dd>
          </dl>
          {e.meta && Object.keys(e.meta).length > 0 && (
            <details className="mt-2">
              <summary className="text-xs text-teal cursor-pointer">Additional metadata</summary>
              <JsonViewer value={e.meta} />
            </details>
          )}
        </Card>
        <Card title="Excerpt">
          {e.excerpt ? <blockquote className="border-l-2 border-teal pl-3 text-[13px] text-gray-800 whitespace-pre-line">{e.excerpt}</blockquote> : <EmptyState compact title="No excerpt captured" />}
        </Card>
      </div>
      <Card title={`Links (${e.links.length})`} bodyClassName="p-0">
        <DataTable columns={cols} rows={e.links} rowKey={(l) => l.id} dense emptyTitle="Not linked to any metric" />
      </Card>

      <Modal open={link} onClose={() => setLink(false)} title="Link evidence to metric" footer={<><button type="button" className="btn-secondary" onClick={() => setLink(false)}>Cancel</button><button type="submit" form="link-form" className="btn-primary" disabled={doLink.isPending || !linkForm.metric_code}>Link</button></>}>
        <form id="link-form" onSubmit={(ev: FormEvent) => { ev.preventDefault(); doLink.mutate(); }} className="space-y-3">
          {doLink.error ? <ErrorBanner error={doLink.error} /> : null}
          <Field label="Metric code" required><Input value={linkForm.metric_code} onChange={(ev) => setLinkForm({ ...linkForm, metric_code: ev.target.value.trim() })} required /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Entity" hint="Leave both blank for a definition-level link"><Input value={linkForm.entity_code} onChange={(ev) => setLinkForm({ ...linkForm, entity_code: ev.target.value })} /></Field>
            <Field label="Period"><Input value={linkForm.period_code} onChange={(ev) => setLinkForm({ ...linkForm, period_code: ev.target.value })} /></Field>
          </div>
          <Field label="Relation"><Select value={linkForm.relation} onChange={(ev) => setLinkForm({ ...linkForm, relation: ev.target.value })}>{['supports', 'contradicts', 'context'].map((r) => <option key={r} value={r}>{r}</option>)}</Select></Field>
          <Field label="Note"><Textarea value={linkForm.note} onChange={(ev) => setLinkForm({ ...linkForm, note: ev.target.value })} /></Field>
        </form>
      </Modal>
      <Modal open={verify} onClose={() => setVerify(false)} title="Verify evidence" footer={<><button type="button" className="btn-secondary" onClick={() => setVerify(false)}>Cancel</button><button type="submit" form="verify-form" className="btn-primary" disabled={doVerify.isPending}>Save</button></>}>
        <form id="verify-form" onSubmit={(ev: FormEvent) => { ev.preventDefault(); doVerify.mutate(); }} className="space-y-3">
          {doVerify.error ? <ErrorBanner error={doVerify.error} /> : null}
          <Field label="Verification status"><Select value={verifyForm.status} onChange={(ev) => setVerifyForm({ ...verifyForm, status: ev.target.value })}>{['verified', 'rejected', 'unverified'].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</Select></Field>
          <Field label="Confidence (0–1)"><Input type="number" min={0} max={1} step="0.05" value={verifyForm.confidence} onChange={(ev) => setVerifyForm({ ...verifyForm, confidence: ev.target.value })} /></Field>
          <Field label="Comment"><Textarea value={verifyForm.comment} onChange={(ev) => setVerifyForm({ ...verifyForm, comment: ev.target.value })} /></Field>
        </form>
      </Modal>
    </div>
  );
}
