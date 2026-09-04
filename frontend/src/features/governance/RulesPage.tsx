import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { FlaskConical, Play, Plus } from 'lucide-react';
import { createRule, runRules, testRule, updateRule, useRules, type RuleIn } from '@/api/governance';
import type { GovernanceRule, RulesRunResult } from '@/api/types';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { Card, DataTable, Drawer, ErrorBanner, Field, Input, JsonDetails, PageHeader, Select, SeverityBadge, StatCard, StatusBadge, Textarea, Toggle, type Column } from '@/components/ui';
import { safeJsonParse } from '@/lib/utils';

const SAMPLE_CONTEXT = JSON.stringify({ metric: { code: 'ENV.GHG.SCOPE1', value: 1200, previous: 1000, yoy_change_pct: 20, evidence_count: 0, is_kpi: true, quality_score: 55, status: 'draft' }, entity: { code: 'ECORP' }, period: { code: 'FY2023' } }, null, 2);

export function RulesPage() {
  const { hasCap } = useAuth();
  const { period } = useAppContext();
  const qc = useQueryClient();
  const [scope, setScope] = useState('');
  const q = useRules(scope || undefined);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<RuleIn>({ code: '', description: '', severity: 'MEDIUM', scope: 'metric_value', condition: '', action: 'WARN', message: '', required_action: '', version: '1.0', approval_status: 'approved' });
  const [ctx, setCtx] = useState(SAMPLE_CONTEXT);
  const [testCondition, setTestCondition] = useState('');
  const [runResult, setRunResult] = useState<RulesRunResult | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: ['governance'] });
  const toggle = useMutation({ mutationFn: (r: GovernanceRule) => updateRule(r.code, { is_active: !r.is_active }), onSuccess: invalidate });
  const create = useMutation({ mutationFn: () => createRule({ ...form, message: form.message || null, required_action: form.required_action || null }), onSuccess: () => { invalidate(); setOpen(false); } });
  const test = useMutation({
    mutationFn: () => {
      const parsed = safeJsonParse(ctx);
      if (!parsed.ok) throw new Error(`Context JSON invalid: ${parsed.error}`);
      return testRule(testCondition || form.condition, parsed.value as Record<string, unknown>);
    },
  });
  const run = useMutation({ mutationFn: () => runRules(period), onSuccess: (r) => { setRunResult(r); invalidate(); } });

  const cols: Column<GovernanceRule>[] = [
    { key: 'code', header: 'Code', render: (r) => <span className="font-mono text-xs text-navy">{r.code}</span> },
    { key: 'severity', header: 'Severity', render: (r) => <SeverityBadge severity={r.severity} /> },
    { key: 'scope', header: 'Scope', render: (r) => <span className="text-xs">{r.scope}</span> },
    { key: 'action', header: 'Action', render: (r) => <span className="badge bg-gray-100 text-gray-700 border-gray-200">{r.action}</span> },
    { key: 'condition', header: 'Condition', render: (r) => <code className="text-xs bg-gray-50 px-1 rounded break-all">{r.condition}</code> },
    { key: 'description', header: 'Description', render: (r) => <span className="text-xs">{r.description}{r.required_action && <span className="block text-[#8F2C22]">Required: {r.required_action}</span>}</span> },
    { key: 'policy_code', header: 'Policy', render: (r) => r.policy_code ?? '—' },
    { key: 'version', header: 'v' },
    { key: 'approval_status', header: 'Approval', render: (r) => <StatusBadge status={r.approval_status} /> },
    { key: 'is_active', header: 'Active', render: (r) => <Toggle checked={r.is_active} onChange={() => toggle.mutate(r)} disabled={!hasCap('governance.manage') || toggle.isPending} label={`Toggle rule ${r.code}`} /> },
    { key: 'test', header: '', render: (r) => <button type="button" className="btn-ghost btn-sm" onClick={() => { setTestCondition(r.condition); setOpen(true); }} aria-label={`Test ${r.code}`}><FlaskConical size={13} /></button> },
  ];

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Governance Rules"
        description="Governance-as-code: declarative rules evaluated against metric values, AI outputs, reports and data changes. Actions include WARN, ESCALATE, REQUIRE_EVIDENCE, REQUIRE_APPROVAL, BLOCK_REPORT_GENERATION and PREVENT_DATA_MODIFICATION."
        actions={
          <>
            <Select value={scope} onChange={(e) => setScope(e.target.value)} className="w-40" aria-label="Scope filter">
              <option value="">All scopes</option>
              {(q.data?.scopes ?? ['metric_value', 'ai_output', 'report', 'data_change', 'requirement']).map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
            {hasCap('metric.validate') && <button type="button" className="btn-secondary" onClick={() => run.mutate()} disabled={run.isPending}><Play size={14} /> {run.isPending ? 'Running…' : `Run rules · ${period}`}</button>}
            {hasCap('governance.manage') && <button type="button" className="btn-primary" onClick={() => { setTestCondition(''); setOpen(true); }}><Plus size={14} /> New rule</button>}
          </>
        }
      />
      {q.error && <ErrorBanner error={q.error} />}
      {toggle.error ? <ErrorBanner error={toggle.error} /> : null}
      {run.error ? <ErrorBanner error={run.error} /> : null}
      {runResult && (
        <Card title="Rules run result" actions={<button type="button" className="btn-ghost btn-sm" onClick={() => setRunResult(null)}>Dismiss</button>}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
            <StatCard label="Evaluated" value={String(runResult.evaluated ?? '—')} />
            <StatCard label="Triggered" value={runResult.triggered?.length ?? 0} tone={runResult.triggered?.length ? 'text-[#9A5A17]' : 'text-navy'} />
            {Object.entries(runResult).filter(([k, v]) => !['evaluated', 'triggered'].includes(k) && typeof v === 'number').map(([k, v]) => <StatCard key={k} label={k.replace(/_/g, ' ')} value={String(v)} />)}
          </div>
          {runResult.triggered?.length ? (
            <table className="table">
              <thead><tr><th>Issue</th><th>Rule</th><th>Severity</th><th>Action</th><th>Metric</th><th>Entity</th></tr></thead>
              <tbody>{runResult.triggered.slice(0, 50).map((t, i) => <tr key={i}><td className="font-mono text-xs">{t.issue}</td><td className="font-mono text-xs">{t.rule}</td><td><SeverityBadge severity={t.severity} /></td><td>{t.action}</td><td className="font-mono text-xs">{t.metric}</td><td>{t.entity}</td></tr>)}</tbody>
            </table>
          ) : (
            <JsonDetails label="Raw result" value={runResult} />
          )}
        </Card>
      )}
      <Card bodyClassName="p-0"><DataTable columns={cols} rows={q.data?.rules} rowKey={(r) => r.id} loading={q.isLoading} dense emptyTitle="No rules" /></Card>

      <Drawer open={open} onClose={() => setOpen(false)} title={testCondition ? 'Test condition' : 'Create rule'} width="max-w-2xl" footer={<><button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Close</button>{!testCondition && hasCap('governance.manage') && <button type="submit" form="rule-form" className="btn-primary" disabled={create.isPending || !form.code || !form.condition}>Create rule</button>}</>}>
        {!testCondition && (
          <form id="rule-form" onSubmit={submit} className="space-y-3">
            {create.error ? <ErrorBanner error={create.error} /> : null}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Code" required><Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.trim().toUpperCase() })} placeholder="GR-KPI-EVIDENCE" required /></Field>
              <Field label="Scope"><Select value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })}>{(q.data?.scopes ?? ['metric_value']).map((s) => <option key={s} value={s}>{s}</option>)}</Select></Field>
              <Field label="Severity"><Select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>{(q.data?.severities ?? ['INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']).map((s) => <option key={s} value={s}>{s}</option>)}</Select></Field>
              <Field label="Action"><Select value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value })}>{(q.data?.actions ?? ['WARN']).map((s) => <option key={s} value={s}>{s}</option>)}</Select></Field>
              <Field label="Version"><Input value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })} /></Field>
              <Field label="Approval status"><Select value={form.approval_status} onChange={(e) => setForm({ ...form, approval_status: e.target.value })}>{['draft', 'approved'].map((s) => <option key={s} value={s}>{s}</option>)}</Select></Field>
            </div>
            <Field label="Description" required><Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} required /></Field>
            <Field label="Condition" required hint="Safe expression over the context, e.g. metric.is_kpi and metric.evidence_count == 0"><Textarea className="font-mono text-xs" value={form.condition} onChange={(e) => setForm({ ...form, condition: e.target.value })} required /></Field>
            <Field label="Message"><Input value={form.message ?? ''} onChange={(e) => setForm({ ...form, message: e.target.value })} /></Field>
            <Field label="Required action"><Input value={form.required_action ?? ''} onChange={(e) => setForm({ ...form, required_action: e.target.value })} /></Field>
            <Field label="Policy code"><Input value={form.policy_code ?? ''} onChange={(e) => setForm({ ...form, policy_code: e.target.value || null })} /></Field>
          </form>
        )}
        <div className={`${testCondition ? '' : 'mt-4 border-t border-gray-200 pt-3'} space-y-3`}>
          <div className="text-sm font-semibold text-navy">Test condition</div>
          {testCondition && <Field label="Condition"><Textarea className="font-mono text-xs" value={testCondition} onChange={(e) => setTestCondition(e.target.value)} /></Field>}
          <Field label="Context (JSON)"><Textarea className="font-mono text-xs min-h-[160px]" value={ctx} onChange={(e) => setCtx(e.target.value)} /></Field>
          <button type="button" className="btn-secondary" onClick={() => test.mutate()} disabled={test.isPending || !(testCondition || form.condition)}><FlaskConical size={14} /> Evaluate</button>
          {test.error ? <ErrorBanner error={test.error} /> : null}
          {test.data && (
            <div className={`text-sm font-medium ${test.data.error ? 'text-[#8F2C22]' : test.data.result ? 'text-[#9A5A17]' : 'text-[#1F7A3A]'}`}>
              {test.data.error ? `Expression error: ${test.data.error}` : test.data.result ? 'Condition is TRUE → rule would trigger' : 'Condition is FALSE → rule would not trigger'}
            </div>
          )}
        </div>
      </Drawer>
    </div>
  );
}
