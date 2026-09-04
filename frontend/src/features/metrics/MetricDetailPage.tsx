import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowDownRight, ArrowUpRight, Minus, Plus, Sparkles } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { askCopilot } from '@/api/agents';
import { setValueStatus, upsertValue, useMetricDetail, type ValueIn } from '@/api/metrics';
import type { AuditEntry, CopilotAnswer, EvidenceItem, MetricDetail } from '@/api/types';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { LineageGraphView, TrendChart } from '@/components/charts';
import { Card, DataTable, DimensionBars, Drawer, EmptyState, ErrorBanner, Field, Input, JsonDetails, LoadingBlock, PageHeader, SeverityBadge, StatCard, StatusBadge, Tabs, Textarea, type Column } from '@/components/ui';
import { scoreTextClass, trendClass } from '@/lib/colors';
import { fmtDateTime, fmtNumber, fmtPct, fmtScore, fmtValue, titleCase, UNAVAILABLE } from '@/lib/format';
import { cn } from '@/lib/utils';
import { CopilotAnswerView } from '../ai/CopilotChat';

const TABS = [
  { key: 'calculation', label: 'Calculation' },
  { key: 'inputs', label: 'Inputs & sources' },
  { key: 'evidence', label: 'Evidence' },
  { key: 'mapping', label: 'Framework mapping' },
  { key: 'quality', label: 'Quality' },
  { key: 'ai', label: 'AI analysis' },
  { key: 'governance', label: 'Governance' },
  { key: 'audit', label: 'Audit history' },
  { key: 'lineage', label: 'Lineage' },
];

function ValueDrawer({ d, open, onClose }: { d: MetricDetail; open: boolean; onClose: () => void }) {
  const { period, entity } = useAppContext();
  const qc = useQueryClient();
  const isText = d.metric.data_type === 'text' || d.metric.kind === 'narrative';
  const [form, setForm] = useState<ValueIn>({ period_code: period, entity_code: entity, value_numeric: d.value?.value_numeric ?? null, value_text: d.value?.value_text ?? null, is_estimate: d.value?.is_estimate ?? false, notes: '', reason: '', evidence_codes: [] });
  const [evidenceText, setEvidenceText] = useState('');
  const m = useMutation({
    mutationFn: () => upsertValue(d.metric.code, { ...form, evidence_codes: evidenceText.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metrics'] });
      qc.invalidateQueries({ queryKey: ['esg'] });
      onClose();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    m.mutate();
  };
  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={`Add / update value · ${d.metric.code}`}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" form="value-form" className="btn-primary" disabled={m.isPending}>{m.isPending ? 'Saving…' : 'Save value'}</button>
        </>
      }
    >
      <form id="value-form" onSubmit={submit} className="space-y-3">
        {m.error ? <ErrorBanner error={m.error} /> : null}
        <p className="text-xs text-gray-600">Scope: <span className="font-medium">{entity}</span> · <span className="font-medium">{period}</span>. The value is saved as a draft, recalculations and quality assessment run, and governance rules are re-evaluated. Input guardrails reject out-of-range values.</p>
        {isText ? (
          <Field label="Text value" required>
            <Textarea value={form.value_text ?? ''} onChange={(e) => setForm({ ...form, value_text: e.target.value })} required />
          </Field>
        ) : (
          <Field label={`Numeric value${d.metric.unit ? ` (${d.metric.unit})` : ''}`} required hint={d.metric.validation_rules ? `Validation: ${JSON.stringify(d.metric.validation_rules)}` : undefined}>
            <Input type="number" step="any" value={form.value_numeric ?? ''} onChange={(e) => setForm({ ...form, value_numeric: e.target.value === '' ? null : Number(e.target.value) })} required />
          </Field>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={!!form.is_estimate} onChange={(e) => setForm({ ...form, is_estimate: e.target.checked })} /> Estimated value
        </label>
        <Field label="Evidence codes" hint="Comma separated evidence codes to link (e.g. EV-2023-P045)">
          <Input value={evidenceText} onChange={(e) => setEvidenceText(e.target.value)} placeholder="EV-…, EV-…" />
        </Field>
        <Field label="Reason for change" required>
          <Input value={form.reason ?? ''} onChange={(e) => setForm({ ...form, reason: e.target.value })} required />
        </Field>
        <Field label="Notes">
          <Textarea value={form.notes ?? ''} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </Field>
      </form>
    </Drawer>
  );
}

function StatusActions({ d }: { d: MetricDetail }) {
  const { hasCap } = useAuth();
  const { period, entity } = useAppContext();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: (status: string) => setValueStatus(d.metric.code, { period_code: period, entity_code: entity, status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['metrics'] }),
  });
  if (!d.value) return null;
  const cur = d.value.status;
  const next: { status: string; cap: string; label: string }[] = [];
  if (cur === 'draft' && hasCap('metric.validate')) next.push({ status: 'validated', cap: 'metric.validate', label: 'Validate' });
  if (cur === 'validated' && hasCap('metric.approve')) next.push({ status: 'approved', cap: 'metric.approve', label: 'Approve' });
  if (cur === 'approved' && hasCap('metric.approve')) next.push({ status: 'final', cap: 'metric.approve', label: 'Mark final' });
  if (cur !== 'draft' && hasCap('data.write')) next.push({ status: 'draft', cap: 'data.write', label: 'Back to draft' });
  return (
    <div className="flex items-center gap-2">
      {m.error ? <ErrorBanner error={m.error} className="py-1" /> : null}
      {next.map((n) => (
        <button key={n.status} type="button" className="btn-secondary btn-sm" onClick={() => m.mutate(n.status)} disabled={m.isPending}>
          {n.label}
        </button>
      ))}
    </div>
  );
}

function AiAnalysis({ d }: { d: MetricDetail }) {
  const { hasCap } = useAuth();
  const { period, entity } = useAppContext();
  const [answer, setAnswer] = useState<CopilotAnswer | null>(null);
  const m = useMutation({ mutationFn: () => askCopilot({ question: d.ai_analysis.suggested_question, period_code: period, entity_code: entity }), onSuccess: setAnswer });
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <button type="button" className="btn-accent" onClick={() => m.mutate()} disabled={m.isPending || !hasCap('ai.run')}>
          <Sparkles size={14} /> {m.isPending ? 'Analysing…' : 'Analyse with Copilot'}
        </button>
        <span className="text-xs text-gray-600">“{d.ai_analysis.suggested_question}”</span>
      </div>
      {!hasCap('ai.run') && <p className="text-xs text-gray-500">Your role does not include the ai.run capability.</p>}
      {m.error ? <ErrorBanner error={m.error} /> : null}
      {answer && (
        <div className="card p-3">
          <CopilotAnswerView a={answer} />
        </div>
      )}
    </div>
  );
}

export function MetricDetailPage() {
  const { code } = useParams();
  const { scope, period, entity } = useAppContext();
  const { hasCap } = useAuth();
  const navigate = useNavigate();
  const q = useMetricDetail(code, scope);
  const [tab, setTab] = useState('calculation');
  const [drawer, setDrawer] = useState(false);

  if (q.isLoading) return <LoadingBlock lines={10} />;
  if (q.error) return <ErrorBanner error={q.error} />;
  const d = q.data;
  if (!d) return <EmptyState />;
  const c = d.card;
  const TrendIcon = c.trend === 'flat' ? Minus : c.trend === 'improving' || c.trend === 'up' ? ArrowUpRight : ArrowDownRight;

  const evidenceCols: Column<EvidenceItem>[] = [
    { key: 'code', header: 'Code', render: (e) => <Link to={`/evidence/${encodeURIComponent(e.code)}`} className="font-mono text-xs text-teal">{e.code}</Link> },
    { key: 'title', header: 'Title', render: (e) => <span className="font-medium">{e.title}</span> },
    { key: 'kind', header: 'Kind', render: (e) => titleCase(e.kind) },
    { key: 'page', header: 'Page', render: (e) => (e.printed_page ? `p. ${e.printed_page}` : e.page_from ? `pdf ${e.page_from}${e.page_to && e.page_to !== e.page_from ? `–${e.page_to}` : ''}` : '—') },
    { key: 'excerpt', header: 'Excerpt', render: (e) => <span className="text-xs text-gray-600 line-clamp-2">{e.excerpt || '—'}</span> },
    { key: 'relation', header: 'Relation', render: (e) => e.relation ?? 'supports' },
    { key: 'verification_status', header: 'Verification', render: (e) => <StatusBadge status={e.verification_status} /> },
  ];
  const auditCols: Column<AuditEntry>[] = [
    { key: 'created_at', header: 'When', render: (a) => fmtDateTime(a.created_at) },
    { key: 'action', header: 'Action', render: (a) => <span className="font-mono text-xs">{a.action}</span> },
    { key: 'object_id', header: 'Object', render: (a) => <span className="font-mono text-xs">{a.object_id}</span> },
    { key: 'user_id', header: 'User', render: (a) => a.user_id ?? 'system' },
    { key: 'reason', header: 'Reason', render: (a) => a.reason ?? '—' },
    { key: 'old', header: 'Old', render: (a) => <JsonDetails label="old" value={a.old_value} /> },
    { key: 'new', header: 'New', render: (a) => <JsonDetails label="new" value={a.new_value} /> },
  ];

  const inputs = Object.entries(d.calculation?.inputs ?? {});

  return (
    <div className="space-y-4">
      <PageHeader
        title={
          <span>
            {d.metric.name} <span className="font-mono text-sm text-gray-500 font-normal">{d.metric.code}</span>
          </span>
        }
        description={d.metric.description ?? undefined}
        actions={
          <>
            <StatusBadge status={d.value?.status ?? 'unavailable'} />
            {d.metric.is_kpi && <span className="badge bg-navy-50 text-navy border-navy-100">KPI</span>}
            <span className="badge bg-gray-100 text-gray-700 border-gray-200">{d.metric.kind}</span>
            {hasCap('data.write') && (
              <button type="button" className="btn-primary btn-sm" onClick={() => setDrawer(true)}>
                <Plus size={13} /> Add value
              </button>
            )}
          </>
        }
      />
      <div className="grid gap-3 grid-cols-2 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label={`Current · ${d.period}`} value={c.value === null ? <span className="text-sm text-gray-400 italic">{UNAVAILABLE}</span> : fmtValue(c.value, d.metric.unit)} hint={c.source_type ? `${titleCase(c.source_type)}${c.is_estimate ? ' · estimate' : ''}` : undefined} />
        <StatCard label={`Previous · ${c.previous_period ?? '—'}`} value={c.previous === null ? <span className="text-sm text-gray-400 italic">{UNAVAILABLE}</span> : fmtValue(c.previous, d.metric.unit)} />
        <StatCard
          label="Year on year"
          value={
            <span className={cn('inline-flex items-center gap-1', trendClass(c.trend))}>
              {c.yoy_pct !== null && <TrendIcon size={18} />} {fmtPct(c.yoy_pct)}
            </span>
          }
          hint={c.trend !== 'flat' ? titleCase(c.trend) : undefined}
        />
        <StatCard label="Target" value={c.target?.value !== null && c.target?.value !== undefined ? fmtValue(c.target.value, d.metric.unit) : <span className="text-sm text-gray-400">No target</span>} hint={c.target ? `${c.target.direction}${c.target.year ? ` by ${c.target.year}` : ''}` : undefined} />
        <StatCard label="Target status" value={c.target_status === 'no_target' ? <span className="text-sm text-gray-400">—</span> : <StatusBadge status={c.target_status} />} />
        <StatCard label="Quality · Evidence · Issues" value={<span className={cn('text-base', scoreTextClass(c.quality_score))}>{fmtScore(c.quality_score)}</span>} hint={`${c.evidence_count} evidence link(s) · ${c.open_issues} open issue(s)`} />
      </div>
      <Card title="Trend" subtitle={`${d.entity.code} · all periods · click a point to open the period value`} actions={<StatusActions d={d} />}>
        <TrendChart
          data={d.series.map((s) => ({ label: s.period, value: s.value, meta: { status: s.status, text: s.text } }))}
          unit={d.metric.unit}
          height={220}
          target={d.targets[0]?.target_value ?? null}
          onPointClick={() => navigate(`/data/lineage?metric=${encodeURIComponent(d.metric.code)}`)}
        />
        {d.metric.kind === 'narrative' && (
          <div className="mt-2 text-[13px] text-gray-700 whitespace-pre-line">{d.value?.value_text ?? <span className="text-gray-400 italic">{UNAVAILABLE}</span>}</div>
        )}
      </Card>
      <Tabs tabs={TABS.map((t) => ({ ...t, count: t.key === 'evidence' ? d.evidence.length : t.key === 'governance' ? d.governance.length + d.issues.length : t.key === 'mapping' ? d.metric.framework_requirements.length : undefined }))} active={tab} onChange={setTab} />

      {tab === 'calculation' && (
        <Card title="Calculation">
          {d.calculation ? (
            <div className="space-y-3">
              <dl className="kv">
                <dt>Formula</dt>
                <dd><code className="bg-gray-50 px-1 rounded">{d.calculation.formula}</code></dd>
                <dt>Version</dt>
                <dd>{d.calculation.version ?? '—'}</dd>
                <dt>Status</dt>
                <dd><StatusBadge status={d.calculation.status} /></dd>
                <dt>Result</dt>
                <dd className="tabular-nums">{fmtValue(d.calculation.result, d.metric.unit)}</dd>
                {d.calculation.message && (
                  <>
                    <dt>Message</dt>
                    <dd>{d.calculation.message}</dd>
                  </>
                )}
                {d.metric.calculation_method && (
                  <>
                    <dt>Method</dt>
                    <dd>{d.metric.calculation_method}</dd>
                  </>
                )}
              </dl>
              <div>
                <div className="label">Inputs</div>
                {inputs.length === 0 ? (
                  <EmptyState compact title="No inputs resolved" />
                ) : (
                  <table className="table">
                    <thead>
                      <tr><th>Input</th><th>Entity</th><th>Period</th><th className="text-right">Value</th></tr>
                    </thead>
                    <tbody>
                      {inputs.map(([k, v]) => (
                        <tr key={k}>
                          <td><Link to={`/metrics/${encodeURIComponent(k.split('@')[0])}`} className="font-mono text-xs text-teal">{k}</Link></td>
                          <td>{v.entity ?? '—'}</td>
                          <td>{v.period ?? '—'}</td>
                          <td className="text-right tabular-nums">{v.value === null || v.value === undefined ? <span className="text-gray-400 italic">{UNAVAILABLE}</span> : fmtNumber(v.value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
              <div>
                <div className="label">Explanation</div>
                {Array.isArray(d.calculation.explanation) ? (
                  <ul className="list-disc pl-5 text-[13px]">
                    {d.calculation.explanation.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                ) : (
                  <p className="text-[13px] whitespace-pre-line">{d.calculation.explanation}</p>
                )}
              </div>
            </div>
          ) : (
            <EmptyState compact title="Not a derived metric" hint={`This ${d.metric.kind} metric is ${d.value?.source_type ? titleCase(d.value.source_type) : 'not calculated'}; aggregation across entities: ${d.metric.aggregation}.`} />
          )}
        </Card>
      )}

      {tab === 'inputs' && (
        <Card title="Inputs & data sources">
          <dl className="kv">
            <dt>Required inputs</dt>
            <dd>{d.metric.required_inputs?.length ? d.metric.required_inputs.map((i) => <Link key={i} to={`/metrics/${encodeURIComponent(i)}`} className="chip mr-1 mb-1 font-mono text-xxs hover:border-teal">{i}</Link>) : '—'}</dd>
            <dt>Data sources</dt>
            <dd>{d.metric.data_sources?.length ? d.metric.data_sources.join(', ') : '—'}</dd>
            <dt>Source type</dt>
            <dd>{d.value?.source_type ? titleCase(d.value.source_type) : '—'}</dd>
            <dt>Dataset version</dt>
            <dd>{d.value?.dataset_version_id ?? '—'}</dd>
            <dt>Aggregation</dt>
            <dd>{d.metric.aggregation}</dd>
            <dt>Frequency</dt>
            <dd>{d.metric.frequency}</dd>
            <dt>Data type</dt>
            <dd>{d.metric.data_type}</dd>
            <dt>Validation rules</dt>
            <dd>{d.metric.validation_rules ? <code className="text-xs">{JSON.stringify(d.metric.validation_rules)}</code> : '—'}</dd>
            <dt>Owner</dt>
            <dd>{d.metric.owner ?? '—'}</dd>
            <dt>Evidence requirements</dt>
            <dd>{d.metric.evidence_requirements ?? (d.metric.evidence_required ? 'Evidence required' : 'Evidence optional')}</dd>
          </dl>
          <div className="mt-3">
            <div className="label">Values by period</div>
            <table className="table">
              <thead><tr><th>Period</th><th className="text-right">Value</th><th>Status</th><th>Source</th></tr></thead>
              <tbody>
                {d.series.map((s) => (
                  <tr key={s.period}>
                    <td>{s.period}</td>
                    <td className="text-right tabular-nums">{s.value === null ? <span className="text-gray-400 italic">{UNAVAILABLE}</span> : fmtValue(s.value, d.metric.unit)}</td>
                    <td><StatusBadge status={s.status} /></td>
                    <td>{s.source_type ? titleCase(s.source_type) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {tab === 'evidence' && (
        <Card title="Evidence" bodyClassName="p-0" actions={<Link to={`/evidence?metric=${encodeURIComponent(d.metric.code)}`} className="text-xs text-teal">Repository view</Link>}>
          <DataTable columns={evidenceCols} rows={d.evidence} rowKey={(e) => `${e.id}-${e.relation}`} emptyTitle="No evidence linked" emptyHint={d.metric.evidence_required ? 'This metric requires evidence. Link a document from the Evidence repository.' : undefined} dense />
        </Card>
      )}

      {tab === 'mapping' && (
        <Card title="Framework requirements" bodyClassName="p-0">
          {d.metric.framework_requirements.length === 0 ? (
            <EmptyState compact title="No framework mapping" />
          ) : (
            <table className="table">
              <thead><tr><th>Requirement</th><th>Title</th><th>Framework</th><th>Version</th><th>Pillar</th><th>Disclosure</th></tr></thead>
              <tbody>
                {d.metric.framework_requirements.map((r) => (
                  <tr key={r.code}>
                    <td><Link to={`/standards/compliance?framework=${r.framework}&q=${encodeURIComponent(r.code)}`} className="font-mono text-xs text-teal">{r.code}</Link></td>
                    <td>{r.title ?? <span className="text-gray-400">Not in registry</span>}</td>
                    <td>{r.framework_name ?? r.framework}</td>
                    <td>{r.version ?? '—'}</td>
                    <td>{r.pillar ?? '—'}</td>
                    <td>{r.disclosure_type ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}

      {tab === 'quality' && (
        <Card title="Data quality" subtitle={d.quality ? `Overall ${fmtScore(d.quality.overall)}` : undefined}>
          {d.quality ? (
            <div className="grid gap-4 md:grid-cols-2">
              <DimensionBars data={Object.entries(d.quality.scores).map(([k, v]) => ({ key: k, value: v }))} />
              <ul className="list-disc pl-5 text-[13px] space-y-1">
                {(d.quality.explanation ?? []).map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </div>
          ) : (
            <EmptyState compact title="Quality not assessed" hint="No value exists for this scope, so no quality score has been computed." />
          )}
        </Card>
      )}

      {tab === 'ai' && (
        <Card title="AI analysis">
          <AiAnalysis d={d} />
        </Card>
      )}

      {tab === 'governance' && (
        <div className="grid gap-3 lg:grid-cols-2">
          <Card title="Triggered rules" bodyClassName="p-0">
            {d.governance.length === 0 ? (
              <EmptyState compact title="No rules triggered" />
            ) : (
              <ul>
                {d.governance.map((g, i) => (
                  <li key={i} className="px-4 py-2 border-b border-gray-100 text-xs">
                    <div className="flex items-center gap-2"><SeverityBadge severity={g.severity} /><span className="font-mono">{g.rule}</span><span className="badge bg-gray-100 text-gray-700 border-gray-200">{g.action}</span></div>
                    <div className="mt-1">{g.message}</div>
                    {g.required_action && <div className="text-[#8F2C22]">Required: {g.required_action}</div>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Open issues" bodyClassName="p-0">
            {d.issues.length === 0 ? (
              <EmptyState compact title="No open issues" />
            ) : (
              <ul>
                {d.issues.map((i) => (
                  <li key={i.id} className="px-4 py-2 border-b border-gray-100 text-xs">
                    <div className="flex items-center gap-2"><SeverityBadge severity={i.severity} /><span className="font-mono text-gray-500">{i.code}</span><StatusBadge status={i.status} />{i.blocks_report && <span className="text-[#8F2C22] font-medium">Blocks report</span>}</div>
                    <div className="mt-1 font-medium">{i.title}</div>
                    {i.required_action && <div className="text-[#8F2C22]">Required: {i.required_action}</div>}
                    <Link to={`/governance/issues?q=${encodeURIComponent(i.code)}`} className="text-teal">Manage</Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      {tab === 'audit' && (
        <Card title="Audit history" bodyClassName="p-0">
          <DataTable columns={auditCols} rows={d.audit_history} rowKey={(a) => a.id} emptyTitle="No audit entries" dense />
        </Card>
      )}

      {tab === 'lineage' && (
        <Card title="Data lineage" subtitle="Metric → calculation → inputs → dataset → source → evidence" actions={<Link to={`/data/lineage?metric=${encodeURIComponent(d.metric.code)}`} className="text-xs text-teal">Open in Lineage</Link>}>
          <LineageGraphView graph={d.lineage} />
        </Card>
      )}

      {drawer && <ValueDrawer d={d} open={drawer} onClose={() => setDrawer(false)} />}
      <p className="text-xxs text-gray-400">Scope: {entity} · {period}. Change the period or entity in the top bar to view other values.</p>
    </div>
  );
}
