import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAgents, useRuns } from '@/api/agents';
import type { AgentRun } from '@/api/types';
import { Card, DataTable, ErrorBanner, PageHeader, Select, StatusBadge, type Column } from '@/components/ui';
import { fmtDateTime, fmtNumber } from '@/lib/format';

export function RunsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const agent = params.get('agent') ?? '';
  const status = params.get('status') ?? '';
  const offset = Number(params.get('offset') ?? 0);
  const limit = 50;
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    if (k !== 'offset') p.delete('offset');
    setParams(p, { replace: true });
  };
  const agents = useAgents();
  const q = useRuns({ agent: agent || undefined, status: status || undefined, limit, offset });
  const cols: Column<AgentRun>[] = [
    { key: 'id', header: '#', align: 'right' },
    { key: 'started_at', header: 'Started', render: (r) => fmtDateTime(r.started_at) },
    { key: 'agent_code', header: 'Agent', render: (r) => <span className="font-mono text-xs">{r.agent_code}</span> },
    { key: 'task', header: 'Task' },
    { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
    { key: 'confidence', header: 'Confidence', align: 'right', render: (r) => (r.confidence === null ? '—' : `${fmtNumber(r.confidence <= 1 ? r.confidence * 100 : r.confidence, { decimals: 0 })}%`) },
    { key: 'expert', header: 'Expert', render: (r) => r.expert ?? '—' },
    { key: 'provider', header: 'Provider', render: (r) => r.provider ?? '—' },
    { key: 'latency_ms', header: 'Latency', align: 'right', render: (r) => (r.latency_ms === null ? '—' : `${fmtNumber(r.latency_ms)} ms`) },
    { key: 'sources', header: 'Sources', align: 'right', render: (r) => r.sources?.length ?? 0 },
    { key: 'error', header: 'Error', render: (r) => <span className="text-xs text-[#8F2C22]">{r.error ?? ''}</span> },
  ];
  return (
    <div className="space-y-4">
      <PageHeader
        title="Agent Runs"
        description="Every agent execution with status, confidence, sources, guardrail results and evaluation."
        showScope={false}
        actions={
          <>
            <Select value={agent} onChange={(e) => set('agent', e.target.value)} className="w-56" aria-label="Agent filter">
              <option value="">All agents</option>
              {(agents.data?.agents ?? []).map((a) => <option key={a.code} value={a.code}>{a.name}</option>)}
            </Select>
            <Select value={status} onChange={(e) => set('status', e.target.value)} className="w-44" aria-label="Status filter">
              <option value="">All statuses</option>
              {['completed', 'requires_review', 'blocked', 'failed'].map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
          </>
        }
      />
      {q.error && <ErrorBanner error={q.error} />}
      <Card bodyClassName="p-0">
        <DataTable columns={cols} rows={q.data?.items} rowKey={(r) => r.id} loading={q.isLoading} onRowClick={(r) => navigate(`/ai/runs/${r.id}`)} pagination={{ total: q.data?.total ?? 0, limit, offset, onChange: (o) => set('offset', String(o)) }} dense emptyTitle="No agent runs yet" />
      </Card>
    </div>
  );
}
