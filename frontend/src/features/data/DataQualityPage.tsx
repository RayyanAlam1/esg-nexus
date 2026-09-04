import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { assessQuality, useQualityScores, useQualitySummary } from '@/api/datasets';
import type { QualityScoreRow } from '@/api/types';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { ComparisonBar } from '@/components/charts';
import { Card, DataTable, DimensionBars, ErrorBanner, LoadingBlock, PageHeader, ScoreRing, Select, type Column } from '@/components/ui';
import { PILLAR_LABEL, scoreTextClass } from '@/lib/colors';
import { fmtScore } from '@/lib/format';
import { cn } from '@/lib/utils';

const DIMS = ['completeness', 'accuracy', 'consistency', 'timeliness', 'validity', 'uniqueness', 'traceability'] as const;

export function DataQualityPage() {
  const { period } = useAppContext();
  const { hasCap } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const summary = useQualitySummary(period);
  const [maxScore, setMaxScore] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const scores = useQualityScores({ period, max_score: maxScore ? Number(maxScore) : undefined, limit, offset });
  const assess = useMutation({ mutationFn: () => assessQuality(period), onSuccess: () => qc.invalidateQueries({ queryKey: ['quality'] }) });

  const cols: Column<QualityScoreRow>[] = [
    { key: 'metric_code', header: 'Metric', render: (r) => <Link to={`/metrics/${encodeURIComponent(r.metric_code)}`} className="font-mono text-xs text-teal">{r.metric_code}</Link> },
    { key: 'metric_name', header: 'Name', render: (r) => r.metric_name },
    { key: 'entity_code', header: 'Entity' },
    { key: 'overall', header: 'Overall', align: 'right', render: (r) => <span className={cn('font-semibold', scoreTextClass(r.overall))}>{fmtScore(r.overall)}</span> },
    ...DIMS.map((d) => ({ key: d, header: d.slice(0, 5) + '.', align: 'right' as const, render: (r: QualityScoreRow) => <span className={scoreTextClass(r[d])}>{fmtScore(r[d])}</span> })),
    { key: 'explanation', header: 'Explanation', render: (r) => <ul className="text-xs text-gray-600 list-disc pl-4">{(r.explanation ?? []).slice(0, 3).map((e, i) => <li key={i}>{e}</li>)}</ul> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Data Quality"
        description="Seven-dimension quality assessment of every metric value in the period: completeness, accuracy, consistency, timeliness, validity, uniqueness, traceability."
        actions={hasCap('metric.validate') && <button type="button" className="btn-secondary" onClick={() => assess.mutate()} disabled={assess.isPending}>{assess.isPending ? 'Assessing…' : `Re-assess ${period}`}</button>}
      />
      {assess.error ? <ErrorBanner error={assess.error} /> : null}
      {summary.isLoading ? (
        <LoadingBlock />
      ) : summary.error ? (
        <ErrorBanner error={summary.error} />
      ) : summary.data ? (
        <div className="grid gap-3 lg:grid-cols-3">
          <Card title="Overall" subtitle={`${summary.data.assessed_values} values assessed · ${summary.data.period}`}>
            <div className="flex items-center gap-6">
              <ScoreRing value={summary.data.overall} label="Average quality" />
              <DimensionBars data={DIMS.map((d) => ({ key: d, value: summary.data?.dimensions[d] ?? null }))} labelWidth={100} />
            </div>
          </Card>
          <Card title="By pillar" subtitle="Average overall score">
            <ComparisonBar data={Object.entries(summary.data.by_pillar).map(([k, v]) => ({ key: k, label: PILLAR_LABEL[k as keyof typeof PILLAR_LABEL] ?? k, value: v }))} height={180} onBarClick={(r) => navigate(`/esg/${r.key}`)} />
          </Card>
          <Card title="Lowest-scoring values" bodyClassName="p-0">
            <ul className="max-h-64 overflow-y-auto">
              {summary.data.lowest.map((l, i) => (
                <li key={i} className="px-4 py-2 border-b border-gray-100 text-xs">
                  <div className="flex items-center justify-between">
                    <Link to={`/metrics/${encodeURIComponent(l.metric_code)}`} className="font-mono text-teal">{l.metric_code}</Link>
                    <span className={cn('font-semibold', scoreTextClass(l.score))}>{fmtScore(l.score)}</span>
                  </div>
                  <div className="text-gray-700">{l.metric_name} · {l.entity}</div>
                  {l.explanation?.[0] && <div className="text-gray-500">{l.explanation[0]}</div>}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      ) : null}
      <Card
        title="Quality scores"
        bodyClassName="p-0"
        actions={
          <Select value={maxScore} onChange={(e) => { setMaxScore(e.target.value); setOffset(0); }} className="w-44" aria-label="Score filter">
            <option value="">All scores</option>
            <option value="80">Below 80</option>
            <option value="60">Below 60</option>
            <option value="40">Below 40</option>
          </Select>
        }
      >
        {scores.error && <ErrorBanner error={scores.error} className="m-3" />}
        <DataTable columns={cols} rows={scores.data?.items} rowKey={(r) => r.id} loading={scores.isLoading} pagination={{ total: scores.data?.total ?? 0, limit, offset, onChange: setOffset }} dense emptyTitle="No quality scores for this period" />
      </Card>
    </div>
  );
}
