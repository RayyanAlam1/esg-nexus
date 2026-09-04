import { useParams } from 'react-router-dom';
import { useRun } from '@/api/agents';
import type { AgentResult, GuardrailResult } from '@/api/types';
import { Card, EmptyState, ErrorBanner, JsonViewer, LoadingBlock, PageHeader, StatusBadge } from '@/components/ui';
import { fmtDateTime, fmtNumber } from '@/lib/format';
import { AgentResultView } from './AgentResultView';

export function RunDetailPage() {
  const { id } = useParams();
  const q = useRun(id ? Number(id) : null);
  if (q.isLoading) return <LoadingBlock lines={8} />;
  if (q.error) return <ErrorBanner error={q.error} />;
  const r = q.data;
  if (!r) return <EmptyState />;
  const asResult: AgentResult = {
    agent: r.agent_code,
    task: r.task,
    status: r.status,
    output: r.output ?? {},
    confidence: r.confidence ?? 0,
    sources: r.sources ?? [],
    metrics_used: [],
    tools_used: r.tools_used ?? [],
    guardrail: (r.guardrail_result ?? {}) as Record<string, unknown> & { input?: GuardrailResult; output?: GuardrailResult },
    evaluation: r.evaluation ? { scores: r.evaluation.scores, overall: r.evaluation.overall, findings: r.evaluation.findings, passed: r.evaluation.passed } : null,
    governance: [],
    run_id: r.id,
    provider: r.provider,
    latency_ms: r.latency_ms ?? 0,
    requires_human_review: r.status === 'requires_review',
    blocked: r.status === 'blocked',
  };
  return (
    <div className="space-y-4">
      <PageHeader title={`Run #${r.id} · ${r.agent_code}`} description={`Task ${r.task} · started ${fmtDateTime(r.started_at)}${r.finished_at ? ` · finished ${fmtDateTime(r.finished_at)}` : ''}`} showScope={false} actions={<StatusBadge status={r.status} />} />
      <Card title="Result">
        <AgentResultView r={asResult} />
        {r.error && <ErrorBanner error={new Error(r.error)} className="mt-3" />}
      </Card>
      <div className="grid gap-3 lg:grid-cols-2">
        <Card title="Input"><JsonViewer value={r.input} /></Card>
        <Card title="Model runs" bodyClassName="p-0">
          {r.model_runs.length === 0 ? (
            <EmptyState compact title="No model calls" hint="Deterministic (offline) execution or tool-only task." />
          ) : (
            <table className="table">
              <thead><tr><th>Provider</th><th>Model</th><th>Purpose</th><th className="text-right">Prompt</th><th className="text-right">Completion</th><th className="text-right">Cache</th><th className="text-right">Latency</th><th>Status</th></tr></thead>
              <tbody>
                {r.model_runs.map((m) => (
                  <tr key={m.id}>
                    <td>{m.provider}</td><td className="text-xs">{m.model}</td><td className="text-xs">{m.purpose}</td>
                    <td className="text-right tabular-nums">{fmtNumber(m.prompt_tokens)}</td><td className="text-right tabular-nums">{fmtNumber(m.completion_tokens)}</td><td className="text-right tabular-nums">{fmtNumber(m.cache_read_tokens)}</td>
                    <td className="text-right tabular-nums">{m.latency_ms === null ? '—' : `${m.latency_ms} ms`}</td><td><StatusBadge status={m.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
      <Card title="Raw output"><JsonViewer value={r.output} maxHeight={480} /></Card>
    </div>
  );
}
