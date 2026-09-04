import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { MaterialityTopic } from '@/api/types';
import { MatrixScatter } from '@/components/charts';
import { Card, EmptyState, ErrorBanner, LoadingBlock, PageHeader, Select, StatusBadge } from '@/components/ui';
import { PILLAR_LABEL } from '@/lib/colors';
import { fmtNumber } from '@/lib/format';
import { useCurrentAssessment } from './MaterialityPage';
import { TopicPanel } from './TopicPanel';

export function MatrixPage() {
  const { list, id, setId, detail } = useCurrentAssessment();
  const [selected, setSelected] = useState<MaterialityTopic | null>(null);
  const d = detail.data;
  return (
    <div className="space-y-4">
      <PageHeader
        title="Materiality Matrix"
        description="Interactive double-materiality matrix. Click a topic to open its scores, rationale, related metrics and evidence."
        showScope={false}
        actions={
          <>
            <Select value={id ?? ''} onChange={(e) => setId(Number(e.target.value))} className="w-72" aria-label="Assessment">
              {(list.data ?? []).map((a) => (
                <option key={a.id} value={a.id}>{a.name} · {a.period_code}</option>
              ))}
            </Select>
            <Link to="/materiality" className="btn-secondary">Assessment</Link>
          </>
        }
      />
      {detail.isLoading ? (
        <LoadingBlock lines={8} />
      ) : detail.error ? (
        <ErrorBanner error={detail.error} />
      ) : !d ? (
        <EmptyState title="No materiality assessment" />
      ) : (
        <div className="grid gap-3 xl:grid-cols-[1fr_360px]">
          <Card title={d.name} subtitle={`${d.period_code} · threshold ${d.threshold} · ${d.topics.filter((t) => t.is_material).length} material of ${d.topics.length}`}>
            <MatrixScatter topics={d.topics} threshold={d.matrix.threshold ?? d.threshold} onSelect={setSelected} selected={selected?.topic_code ?? null} xLabel={d.matrix.x_axis} yLabel={d.matrix.y_axis} />
          </Card>
          <Card title="Topics (table view)" bodyClassName="p-0">
            <ul className="max-h-[520px] overflow-y-auto">
              {[...d.topics].sort((a, b) => Math.max(b.impact_score ?? 0, b.financial_score ?? 0) - Math.max(a.impact_score ?? 0, a.financial_score ?? 0)).map((t) => (
                <li key={t.topic_code}>
                  <button type="button" className={`w-full text-left px-3 py-2 border-b border-gray-100 hover:bg-navy-50/60 ${selected?.topic_code === t.topic_code ? 'bg-navy-50' : ''}`} onClick={() => setSelected(t)}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[13px] font-medium truncate">{t.name}</span>
                      <StatusBadge status={t.is_material ? 'complete' : 'draft'} label={t.is_material ? 'Material' : '—'} />
                    </div>
                    <div className="text-xs text-gray-500 tabular-nums">{PILLAR_LABEL[t.pillar]} · impact {fmtNumber(t.impact_score, { decimals: 2 })} · financial {fmtNumber(t.financial_score, { decimals: 2 })} · stakeholder {fmtNumber(t.stakeholder_priority, { decimals: 1 })}</div>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          <TopicPanel assessmentId={d.id} topic={selected} threshold={d.threshold} onClose={() => setSelected(null)} />
        </div>
      )}
    </div>
  );
}
