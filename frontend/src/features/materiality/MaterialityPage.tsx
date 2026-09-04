import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { analyzeMateriality, useAssessment, useAssessments } from '@/api/materiality';
import type { AgentResult, MaterialityTopic, StakeholderInput } from '@/api/types';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { Card, DataTable, EmptyState, ErrorBanner, LoadingBlock, PageHeader, Select, StatCard, StatusBadge, type Column } from '@/components/ui';
import { PILLAR_LABEL } from '@/lib/colors';
import { fmtNumber } from '@/lib/format';
import { AgentResultView } from '../ai/AgentResultView';
import { TopicPanel } from './TopicPanel';

export function useCurrentAssessment() {
  const list = useAssessments();
  const [id, setId] = useState<number | null>(null);
  useEffect(() => {
    if (list.data?.length && id === null) setId(list.data[0].id);
  }, [list.data, id]);
  const detail = useAssessment(id);
  return { list, id, setId, detail };
}

export function MaterialityPage() {
  const { hasCap } = useAuth();
  const { period } = useAppContext();
  const qc = useQueryClient();
  const { list, id, setId, detail } = useCurrentAssessment();
  const [selected, setSelected] = useState<MaterialityTopic | null>(null);
  const [analysis, setAnalysis] = useState<AgentResult | null>(null);
  const analyze = useMutation({ mutationFn: () => analyzeMateriality(period), onSuccess: (r) => { setAnalysis(r); qc.invalidateQueries({ queryKey: ['materiality'] }); } });

  const tcols: Column<MaterialityTopic>[] = [
    { key: 'name', header: 'Topic', render: (t) => <span className="font-medium">{t.name}</span> },
    { key: 'pillar', header: 'Pillar', render: (t) => PILLAR_LABEL[t.pillar] ?? t.pillar },
    { key: 'impact_score', header: 'Impact', align: 'right', render: (t) => fmtNumber(t.impact_score, { decimals: 2 }) },
    { key: 'financial_score', header: 'Financial', align: 'right', render: (t) => fmtNumber(t.financial_score, { decimals: 2 }) },
    { key: 'stakeholder_priority', header: 'Stakeholder', align: 'right', render: (t) => fmtNumber(t.stakeholder_priority, { decimals: 1 }) },
    { key: 'is_material', header: 'Material', render: (t) => <StatusBadge status={t.is_material ? 'complete' : 'draft'} label={t.is_material ? 'Material' : 'Not material'} /> },
    { key: 'related_metrics', header: 'Metrics', align: 'right', render: (t) => t.related_metrics.length },
    { key: 'risks', header: 'Risks / Opps', align: 'right', render: (t) => `${t.risks?.length ?? 0} / ${t.opportunities?.length ?? 0}` },
  ];
  const scols: Column<StakeholderInput>[] = [
    { key: 'stakeholder_group', header: 'Stakeholder group', render: (s) => <span className="font-medium">{s.stakeholder_group}</span> },
    { key: 'topic_code', header: 'Topic', render: (s) => detail.data?.topics.find((t) => t.topic_code === s.topic_code)?.name ?? s.topic_code ?? '—' },
    { key: 'priority', header: 'Priority', align: 'right', render: (s) => fmtNumber(s.priority, { decimals: 1 }) },
    { key: 'channel', header: 'Channel', render: (s) => s.channel ?? '—' },
    { key: 'concern', header: 'Concern', render: (s) => <span className="text-xs text-gray-700">{s.concern ?? '—'}</span> },
    { key: 'engagement_value', header: 'Value of engagement', render: (s) => <span className="text-xs text-gray-600">{s.engagement_value ?? '—'}</span> },
  ];

  const d = detail.data;
  return (
    <div className="space-y-4">
      <PageHeader
        title="Materiality Assessment"
        description="Double materiality: impact (severity × likelihood) and financial (magnitude × likelihood) scores per topic, stakeholder inputs and rationale."
        actions={
          <>
            <Select value={id ?? ''} onChange={(e) => setId(Number(e.target.value))} className="w-72" aria-label="Assessment">
              {(list.data ?? []).map((a) => (
                <option key={a.id} value={a.id}>{a.name} · {a.period_code}</option>
              ))}
            </Select>
            <Link to="/materiality/matrix" className="btn-secondary">Matrix</Link>
            {hasCap('ai.run') && (
              <button type="button" className="btn-accent" onClick={() => analyze.mutate()} disabled={analyze.isPending}>
                <Sparkles size={14} /> {analyze.isPending ? 'Analysing…' : 'Analyze with Materiality Agent'}
              </button>
            )}
          </>
        }
      />
      {list.error && <ErrorBanner error={list.error} />}
      {analyze.error ? <ErrorBanner error={analyze.error} /> : null}
      {detail.isLoading ? (
        <LoadingBlock lines={6} />
      ) : detail.error ? (
        <ErrorBanner error={detail.error} />
      ) : !d ? (
        <EmptyState title="No materiality assessment" />
      ) : (
        <>
          <div className="grid gap-3 grid-cols-2 md:grid-cols-5">
            <StatCard label="Approach" value={<span className="text-sm capitalize">{d.approach}</span>} hint={d.methodology ?? undefined} />
            <StatCard label="Threshold" value={d.threshold} hint="Material when max(impact, financial) ≥ threshold" />
            <StatCard label="Topics" value={d.topics.length} />
            <StatCard label="Material topics" value={d.topics.filter((t) => t.is_material).length} tone="text-teal" />
            <StatCard label="Status" value={<StatusBadge status={d.status} />} hint={`Period ${d.period_code}`} />
          </div>
          {analysis && (
            <Card title="Materiality Agent analysis" actions={<button type="button" className="btn-ghost btn-sm" onClick={() => setAnalysis(null)}>Dismiss</button>}>
              <AgentResultView r={analysis} />
            </Card>
          )}
          <Card title="Topics" bodyClassName="p-0" subtitle="Click a topic to view scores, rationale, risks, opportunities, related metrics and evidence, or to edit scores.">
            <DataTable columns={tcols} rows={d.topics} rowKey={(t) => t.topic_code} onRowClick={setSelected} dense emptyTitle="No topics" />
          </Card>
          <Card title="Stakeholder inputs" bodyClassName="p-0">
            <DataTable columns={scols} rows={d.stakeholder_inputs} rowKey={(s) => s.id} dense emptyTitle="No stakeholder inputs recorded" />
          </Card>
          <TopicPanel assessmentId={d.id} topic={selected} threshold={d.threshold} onClose={() => setSelected(null)} />
        </>
      )}
    </div>
  );
}
