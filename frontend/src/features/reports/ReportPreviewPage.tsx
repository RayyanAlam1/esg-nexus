import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Download, FileText, RefreshCw } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { downloadVersion, generateReport, regenerateSection, transitionReport, updateSection, usePreview, useReport, validateReport } from '@/api/reports';
import type { ReportSection, ValidationResult } from '@/api/types';
import { useAuth } from '@/app/auth';
import { Card, DimensionBars, Drawer, EmptyState, ErrorBanner, Field, LoadingBlock, MarkdownView, PageHeader, ScoreRing, StatusBadge, Textarea } from '@/components/ui';
import { fmtBytes, fmtDateTime, titleCase } from '@/lib/format';
import { cn } from '@/lib/utils';
import { ValidationChecks } from './ReportBuilderPage';

const FORMATS = ['pdf', 'docx', 'xlsx', 'csv'];

export function ReportPreviewPage() {
  const { id } = useParams();
  const reportId = id ? Number(id) : null;
  const { hasCap } = useAuth();
  const qc = useQueryClient();
  const report = useReport(reportId);
  const preview = usePreview(reportId);
  const [page, setPage] = useState(0);
  const [editing, setEditing] = useState<ReportSection | null>(null);
  const [md, setMd] = useState('');
  const [comment, setComment] = useState('');
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [lastGenerated, setLastGenerated] = useState<string | null>(null);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['reports'] });
  };
  const onError = (e: unknown) => setActionError(e);
  const save = useMutation({ mutationFn: (state: string) => updateSection(reportId as number, (editing as ReportSection).code, { content_md: md, state, comment: comment || null }), onSuccess: () => { invalidate(); setEditing(null); setActionError(null); }, onError });
  const sectionState = useMutation({ mutationFn: (p: { code: string; state: string }) => updateSection(reportId as number, p.code, { state: p.state }), onSuccess: () => { invalidate(); setActionError(null); }, onError });
  const regen = useMutation({ mutationFn: (code: string) => regenerateSection(reportId as number, code), onSuccess: () => { invalidate(); setActionError(null); }, onError });
  const validate = useMutation({ mutationFn: () => validateReport(reportId as number), onSuccess: (v) => { setValidation(v); invalidate(); setActionError(null); }, onError });
  const transition = useMutation({ mutationFn: (state: string) => transitionReport(reportId as number, state), onSuccess: () => { invalidate(); setActionError(null); }, onError });
  const generate = useMutation({ mutationFn: (p: { format: string; final: boolean }) => generateReport(reportId as number, p.format, p.final), onSuccess: (v) => { invalidate(); setActionError(null); setLastGenerated(`${v.format.toUpperCase()} v${v.version}${v.is_final ? ' (final)' : ' (draft)'} generated`); }, onError });

  const pages = preview.data?.pages ?? [];
  useEffect(() => {
    if (page >= pages.length) setPage(0);
  }, [pages.length, page]);
  const current = pages[page];
  const r = report.data;
  const section = useMemo(() => r?.sections.find((s) => s.code === current?.code) ?? null, [r, current]);
  const readiness = (r?.readiness ?? preview.data?.readiness ?? {}) as { overall?: number; components?: Record<string, number> };
  const validationResult = validation ?? r?.validation_result ?? null;
  const canApproveSection = hasCap('report.approve');
  const canReview = hasCap('review');
  const canBuild = hasCap('report.build');
  const busy = save.isPending || sectionState.isPending || regen.isPending || validate.isPending || transition.isPending || generate.isPending;

  if (report.isLoading || preview.isLoading) return <LoadingBlock lines={10} />;
  if (report.error) return <ErrorBanner error={report.error} />;
  if (preview.error) return <ErrorBanner error={preview.error} />;
  if (!r || !preview.data) return <EmptyState />;

  return (
    <div className="space-y-3">
      <PageHeader
        title={<span>{r.title} <span className="text-sm font-normal text-gray-500">#{r.id}</span></span>}
        description={`${r.organization_name} · ${r.period_code} · ${r.framework_codes.join(', ')} · template ${r.template_code}${r.locked ? ' · locked' : ''}`}
        showScope={false}
        actions={
          <>
            <StatusBadge status={r.status} />
            {canBuild && <button type="button" className="btn-secondary btn-sm" onClick={() => validate.mutate()} disabled={busy}>Validate</button>}
            {canApproveSection && r.status !== 'approved' && r.status !== 'published' && <button type="button" className="btn-primary btn-sm" onClick={() => transition.mutate('approved')} disabled={busy}>Approve report</button>}
            {hasCap('report.publish') && r.status === 'approved' && <button type="button" className="btn-accent btn-sm" onClick={() => transition.mutate('published')} disabled={busy}>Publish</button>}
            {canBuild && canApproveSection && <button type="button" className="btn-accent btn-sm" onClick={() => generate.mutate({ format: 'pdf', final: true })} disabled={busy}><FileText size={13} /> Generate final report</button>}
          </>
        }
      />
      {actionError ? <ErrorBanner error={actionError} /> : null}
      {lastGenerated && <div className="text-xs text-[#1F7A3A]">{lastGenerated}</div>}

      <div className="grid gap-3 xl:grid-cols-[220px_1fr_300px]">
        <aside className="card p-2 h-fit xl:sticky xl:top-0 max-h-[80vh] overflow-y-auto">
          <div className="label px-1">Contents</div>
          <ol>
            {pages.map((p, i) => (
              <li key={p.number}>
                <button type="button" onClick={() => setPage(i)} className={cn('w-full text-left px-2 py-1.5 rounded text-xs flex items-center justify-between gap-1', i === page ? 'bg-navy text-white' : 'hover:bg-gray-100 text-gray-700')}>
                  <span className="truncate">{p.number}. {p.title}</span>
                  {p.status && <span className={cn('w-2 h-2 rounded-full shrink-0', ['approved', 'published'].includes(p.status) ? 'bg-[#1F7A3A]' : p.status === 'blocked' ? 'bg-[#B03A2E]' : ['requires_review', 'reviewed', 'ai_generated'].includes(p.status) ? 'bg-[#C9A227]' : 'bg-gray-300')} title={p.status} />}
                </button>
              </li>
            ))}
          </ol>
        </aside>

        <div className="min-w-0">
          <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
            <div className="flex items-center gap-1">
              <button type="button" className="btn-secondary btn-sm" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0} aria-label="Previous page"><ChevronLeft size={14} /></button>
              <span className="text-xs text-gray-600 tabular-nums px-1">Page {current?.number ?? 0} of {pages.length}</span>
              <button type="button" className="btn-secondary btn-sm" onClick={() => setPage((p) => Math.min(pages.length - 1, p + 1))} disabled={page >= pages.length - 1} aria-label="Next page"><ChevronRight size={14} /></button>
            </div>
            {section && (
              <div className="flex items-center gap-1 flex-wrap">
                <StatusBadge status={section.status} />
                <span className="text-xxs text-gray-500">v{section.version} · {section.narrative_source}</span>
                {(canBuild || canReview) && <button type="button" className="btn-secondary btn-sm" onClick={() => { setEditing(section); setMd(section.content_md ?? ''); setComment(''); }} disabled={busy || r.locked}>Edit</button>}
                {canBuild && <button type="button" className="btn-secondary btn-sm" onClick={() => regen.mutate(section.code)} disabled={busy || r.locked}><RefreshCw size={12} /> Regenerate</button>}
                {canBuild && <button type="button" className="btn-secondary btn-sm" onClick={() => validate.mutate()} disabled={busy}>Validate</button>}
                {canReview && section.status !== 'reviewed' && section.status !== 'approved' && <button type="button" className="btn-secondary btn-sm" onClick={() => sectionState.mutate({ code: section.code, state: 'reviewed' })} disabled={busy}>Mark reviewed</button>}
                {canApproveSection && section.status !== 'approved' && section.status !== 'published' && <button type="button" className="btn-primary btn-sm" onClick={() => sectionState.mutate({ code: section.code, state: 'approved' })} disabled={busy}>Approve section</button>}
              </div>
            )}
          </div>
          <style>{preview.data.css}</style>
          <div className="paper">
            {current ? <div className="page" dangerouslySetInnerHTML={{ __html: current.html }} /> : <EmptyState title="No pages" />}
          </div>
        </div>

        <aside className="space-y-3">
          <Card title="Readiness" bodyClassName="p-3">
            <div className="flex items-center gap-3">
              <ScoreRing value={typeof readiness.overall === 'number' ? readiness.overall : null} size={84} stroke={8} />
              <div className="flex-1">
                {readiness.components ? <DimensionBars data={Object.entries(readiness.components).map(([k, v]) => ({ key: k, value: v }))} labelWidth={92} /> : <p className="text-xs text-gray-500">Validate the report to compute readiness.</p>}
              </div>
            </div>
          </Card>
          <Card title="Validation" bodyClassName="p-3">
            {validationResult ? <ValidationChecks v={validationResult} /> : <p className="text-xs text-gray-500">Not validated yet.</p>}
          </Card>
          <Card title="Sections" bodyClassName="p-0">
            <ul className="max-h-64 overflow-y-auto">
              {r.sections.map((s) => (
                <li key={s.code} className="px-3 py-1.5 border-b border-gray-100 text-xs flex items-center justify-between gap-2">
                  <span className={cn('truncate', s.level >= 2 && 'pl-2')}>{s.title}</span>
                  <StatusBadge status={s.status} />
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Files" bodyClassName="p-3">
            {canBuild && (
              <div className="flex flex-wrap gap-1 mb-2">
                {FORMATS.map((f) => <button key={f} type="button" className="btn-secondary btn-sm uppercase" onClick={() => generate.mutate({ format: f, final: false })} disabled={busy}>Draft {f}</button>)}
              </div>
            )}
            {r.versions.length === 0 ? <p className="text-xs text-gray-500">No files generated.</p> : (
              <ul className="space-y-1">
                {[...r.versions].sort((a, b) => b.version - a.version).map((v) => (
                  <li key={v.id} className="text-xs flex items-center justify-between gap-2">
                    <span>v{v.version} <span className="uppercase font-mono">{v.format}</span> {v.is_final ? <span className="badge bg-green-50 text-[#1F6B33] border-green-200">final</span> : <span className="badge bg-gray-100 text-gray-600 border-gray-200">draft</span>}<span className="block text-gray-500">{fmtDateTime(v.created_at)} · {fmtBytes(v.size_bytes)}</span></span>
                    <button type="button" className="btn-ghost btn-sm" onClick={() => downloadVersion(v).catch(onError)} aria-label={`Download v${v.version} ${v.format}`}><Download size={13} /></button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </aside>
      </div>

      <Drawer open={!!editing} onClose={() => setEditing(null)} title={editing ? `Edit · ${editing.title}` : ''} width="max-w-3xl" footer={<><button type="button" className="btn-secondary" onClick={() => setEditing(null)}>Cancel</button><button type="button" className="btn-secondary" onClick={() => save.mutate('draft')} disabled={save.isPending}>Save as draft</button><button type="button" className="btn-primary" onClick={() => save.mutate('requires_review')} disabled={save.isPending}>Save & request review</button></>}>
        {editing && (
          <div className="grid gap-3 lg:grid-cols-2">
            <div className="space-y-2">
              {save.error ? <ErrorBanner error={save.error} /> : null}
              <Field label="Content (Markdown)"><Textarea className="font-mono text-xs min-h-[420px]" value={md} onChange={(e) => setMd(e.target.value)} /></Field>
              <Field label="Comment"><Textarea value={comment} onChange={(e) => setComment(e.target.value)} className="min-h-[50px]" /></Field>
              <p className="text-xxs text-gray-500">Metrics: {(editing.metric_codes ?? []).join(', ') || '—'} · Disclosures: {(editing.requirement_codes ?? []).join(', ') || '—'}. Numbers in narrative must match governed metric values (numerical consistency check).</p>
            </div>
            <div>
              <div className="label">Preview</div>
              <div className="border border-gray-200 rounded p-3 max-h-[540px] overflow-y-auto"><MarkdownView content={md} /></div>
              {editing.comments?.length ? (
                <div className="mt-2"><div className="label">History</div><ul className="text-xxs text-gray-600 space-y-0.5">{editing.comments.slice(-5).map((c, i) => <li key={i}>{fmtDateTime(c.at)} · {c.by} → {titleCase(c.state)}{c.note ? `: ${c.note}` : ''}</li>)}</ul></div>
              ) : null}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
