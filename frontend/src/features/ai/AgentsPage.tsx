import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Play } from 'lucide-react';
import { runAgent, useAgents } from '@/api/agents';
import type { AgentResult, AgentSpec } from '@/api/types';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { Card, ErrorBanner, Field, Input, LoadingBlock, Modal, PageHeader, StatusBadge, Textarea } from '@/components/ui';
import { fmtNumber } from '@/lib/format';
import { safeJsonParse } from '@/lib/utils';
import { AgentResultView } from './AgentResultView';

const DEFAULT_TASK: Record<string, string> = {
  standards_mapping_agent: 'gap_analysis',
  calculation_agent: 'explain',
  evidence_agent: 'review',
  governance_agent: 'check',
  assurance_agent: 'package',
  materiality_agent: 'assess',
  esg_data_agent: 'classify_dataset',
};

export function AgentsPage() {
  const { hasCap } = useAuth();
  const { period, entity } = useAppContext();
  const qc = useQueryClient();
  const q = useAgents();
  const [agent, setAgent] = useState<AgentSpec | null>(null);
  const [task, setTask] = useState('answer');
  const [payload, setPayload] = useState('{}');
  const [result, setResult] = useState<AgentResult | null>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: (p: Record<string, unknown>) => runAgent((agent as AgentSpec).code, task, p),
    onSuccess: (r) => {
      setResult(r);
      qc.invalidateQueries({ queryKey: ['agents'] });
    },
  });
  const openRun = (a: AgentSpec) => {
    setAgent(a);
    setTask(DEFAULT_TASK[a.code] ?? 'answer');
    setPayload(JSON.stringify({ question: `Summarise the key findings for ${period}.`, period_code: period, entity_code: entity }, null, 2));
    setResult(null);
    setJsonError(null);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const parsed = safeJsonParse(payload);
    if (!parsed.ok) {
      setJsonError(parsed.error);
      return;
    }
    setJsonError(null);
    run.mutate((parsed.value ?? {}) as Record<string, unknown>);
  };

  return (
    <div className="space-y-4">
      <PageHeader title="AI Agents" description={q.data ? `Provider: ${q.data.provider} · model: ${q.data.model}. Every run is guardrailed, evaluated and governance-checked before its output is used.` : undefined} showScope={false} />
      {q.isLoading ? (
        <LoadingBlock lines={6} />
      ) : q.error ? (
        <ErrorBanner error={q.error} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(q.data?.agents ?? []).map((a) => (
            <Card key={a.code} title={a.name} subtitle={<span className="font-mono">{a.code} · v{a.version} · expert {a.expert}</span>} actions={<StatusBadge status={a.is_active ? 'active' : 'retired'} />}>
              <p className="text-xs text-gray-700 mb-2">{a.description}</p>
              <ul className="list-disc pl-4 text-xs text-gray-600 space-y-0.5 mb-2">{a.responsibilities.slice(0, 4).map((r, i) => <li key={i}>{r}</li>)}</ul>
              <div className="flex flex-wrap gap-1 mb-3">{a.tools.map((t) => <span key={t} className="chip font-mono text-xxs">{t}</span>)}</div>
              <div className="flex items-center justify-between text-xs text-gray-600">
                <span>{a.runs} run(s) · avg confidence {a.avg_confidence === null ? '—' : fmtNumber(a.avg_confidence * (a.avg_confidence <= 1 ? 100 : 1), { decimals: 0 }) + '%'}</span>
                {hasCap('ai.run') && <button type="button" className="btn-primary btn-sm" onClick={() => openRun(a)}><Play size={12} /> Run</button>}
              </div>
            </Card>
          ))}
        </div>
      )}
      <Modal open={!!agent} onClose={() => setAgent(null)} title={`Run ${agent?.name ?? ''}`} width="max-w-3xl" footer={<><button type="button" className="btn-secondary" onClick={() => setAgent(null)}>Close</button><button type="submit" form="run-form" className="btn-primary" disabled={run.isPending}>{run.isPending ? 'Running…' : 'Run agent'}</button></>}>
        <form id="run-form" onSubmit={submit} className="space-y-3">
          {run.error ? <ErrorBanner error={run.error} /> : null}
          <Field label="Task"><Input value={task} onChange={(e) => setTask(e.target.value)} /></Field>
          <Field label="Payload (JSON)" hint={jsonError ? <span className="text-[#8F2C22]">{jsonError}</span> : 'Keys such as question, period_code, entity_code, framework_code, metric_code depending on the task.'}>
            <Textarea className="font-mono text-xs min-h-[140px]" value={payload} onChange={(e) => setPayload(e.target.value)} />
          </Field>
        </form>
        {result && (
          <div className="mt-4 border-t border-gray-200 pt-3">
            <AgentResultView r={result} />
          </div>
        )}
      </Modal>
    </div>
  );
}
