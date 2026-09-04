import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useEvaluationSummary, useEvaluationTrend, useEvaluations } from '@/api/agents';
import type { EvaluationRow } from '@/api/types';
import { useAppContext } from '@/app/context';
import { TrendChart } from '@/components/charts';
import { Card, DataTable, DimensionBars, ErrorBanner, JsonDetails, LoadingBlock, PageHeader, ScoreRing, Select, StatCard, StatusBadge, type Column } from '@/components/ui';
import { fmtDateTime, fmtNumber, fmtScore, titleCase } from '@/lib/format';

export function EvaluationPage() {
  const { period } = useAppContext();
  const navigate = useNavigate();
  const summary = useEvaluationSummary(period);
  const trend = useEvaluationTrend();
  const [dimension, setDimension] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const list = useEvaluations({ dimension: dimension || undefined, limit, offset });
  const s = summary.data;

  const cols: Column<EvaluationRow>[] = [
    { key: 'created_at', header: 'When', render: (e) => fmtDateTime(e.created_at) },
    { key: 'dimension', header: 'Dimension', render: (e) => titleCase(e.dimension) },
    { key: 'object', header: 'Object', render: (e) => <span className="font-mono text-xs">{e.object_type}:{e.object_id}</span> },
    { key: 'evaluator', header: 'Evaluator' },
    { key: 'overall', header: 'Overall', align: 'right', render: (e) => fmtScore(e.overall) },
    { key: 'passed', header: 'Result', render: (e) => <StatusBadge status={e.passed ? 'passed' : 'failed'} /> },
    { key: 'scores', header: 'Scores', render: (e) => <span className="text-xs text-gray-600">{Object.entries(e.scores).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(' · ')}</span> },
    { key: 'findings', header: 'Findings', render: (e) => (e.findings?.length ? <JsonDetails label={`${e.findings.length} finding(s)`} value={e.findings} /> : '—') },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title="Evaluation Centre" description="Quality scoring across AI outputs, data, evidence, framework alignment and report readiness, with model observability." />
      {summary.isLoading ? (
        <LoadingBlock />
      ) : summary.error ? (
        <ErrorBanner error={summary.error} />
      ) : s ? (
        <>
          <div className="grid gap-3 grid-cols-2 md:grid-cols-5">
            {[
              ['AI Quality', s.overall_scores.ai_quality, 'evaluated agent outputs'],
              ['Data Quality', s.overall_scores.data_quality, 'average of quality scores'],
              ['Evidence Coverage', s.overall_scores.evidence_coverage, 'values linked to evidence'],
              ['Framework Alignment', s.overall_scores.framework_alignment, 'WEF SCM · UNGC · UN SDG'],
              ['Report Readiness', s.overall_scores.report_readiness, 'weighted readiness'],
            ].map(([label, value, hint]) => (
              <Card key={label as string} bodyClassName="flex flex-col items-center p-3">
                <ScoreRing value={value as number | null} size={96} stroke={8} label={label as string} sublabel={hint as string} />
              </Card>
            ))}
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            <Card title="AI quality dimensions" subtitle={`${s.ai_quality.evaluated_outputs} evaluated output(s)${s.ai_quality.hallucination_rate !== null && s.ai_quality.hallucination_rate !== undefined ? ` · hallucination rate ${fmtNumber(s.ai_quality.hallucination_rate, { decimals: 1 })}%` : ''}`}>
              {Object.keys(s.ai_quality.dimensions).length === 0 ? <p className="text-xs text-gray-500">No AI outputs evaluated yet. Run an agent or ask the Copilot.</p> : <DimensionBars data={Object.entries(s.ai_quality.dimensions).map(([k, v]) => ({ key: k, value: v }))} />}
            </Card>
            <Card title="Data & ESG quality">
              <DimensionBars data={[
                { key: 'completeness', value: s.data_quality.completeness },
                { key: 'accuracy', value: s.data_quality.accuracy },
                { key: 'consistency', value: s.data_quality.consistency },
                { key: 'disclosure_completeness', value: s.esg_quality.disclosure_completeness },
                ...Object.entries(s.esg_quality.framework_alignment).map(([k, v]) => ({ key: k, label: `Alignment · ${k}`, value: v })),
              ]} labelWidth={170} />
              <p className="text-xs text-gray-500 mt-2">{s.esg_quality.metric_coverage} metrics with quality scores in {s.period}.</p>
            </Card>
            <Card title="Observability">
              <div className="grid grid-cols-2 gap-2">
                <StatCard label="Model runs" value={fmtNumber(s.observability.model_runs)} />
                <StatCard label="Guardrail blocks" value={fmtNumber(s.observability.guardrail_blocks)} tone={s.observability.guardrail_blocks ? 'text-[#8F2C22]' : 'text-navy'} />
                <StatCard label="Prompt tokens" value={fmtNumber(s.observability.prompt_tokens, { compact: true })} />
                <StatCard label="Completion tokens" value={fmtNumber(s.observability.completion_tokens, { compact: true })} />
                <StatCard label="Avg latency" value={`${fmtNumber(s.observability.avg_model_latency_ms)} ms`} />
                {s.report_quality && <StatCard label="Report checks" value={`${s.report_quality.checks_passed}/${s.report_quality.checks_total}`} hint={`report #${s.report_quality.report_id} · ${s.report_quality.status}`} onClick={() => navigate(`/reports/${s.report_quality?.report_id}/preview`)} />}
              </div>
            </Card>
          </div>
          <Card title="Readiness components">
            <DimensionBars data={Object.entries(s.readiness.components).map(([k, v]) => ({ key: k, value: v }))} labelWidth={170} />
          </Card>
        </>
      ) : null}
      <Card title="AI evaluation trend" subtitle="Overall score per evaluated output (last 100)">
        {trend.error ? <ErrorBanner error={trend.error} /> : <TrendChart data={(trend.data ?? []).map((t) => ({ label: fmtDateTime(t.at), value: t.overall, meta: { object: t.object } }))} height={200} compactAxis primaryLabel="Overall" />}
      </Card>
      <Card title="Evaluations" bodyClassName="p-0" actions={<Select value={dimension} onChange={(e) => { setDimension(e.target.value); setOffset(0); }} className="w-40" aria-label="Dimension"><option value="">All dimensions</option>{['ai', 'data', 'esg', 'report'].map((d) => <option key={d} value={d}>{d}</option>)}</Select>}>
        {list.error && <ErrorBanner error={list.error} className="m-3" />}
        <DataTable columns={cols} rows={list.data?.items} rowKey={(e) => e.id} loading={list.isLoading} pagination={{ total: list.data?.total ?? 0, limit, offset, onChange: setOffset }} onRowClick={(e) => e.object_type === 'agent_run' && navigate(`/ai/runs/${e.object_id}`)} dense emptyTitle="No evaluations recorded" />
      </Card>
    </div>
  );
}
