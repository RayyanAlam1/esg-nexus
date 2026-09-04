import { useNavigate } from 'react-router-dom';
import { useEntityComparison } from '@/api/esg';
import { useMetricDetail } from '@/api/metrics';
import { useAppContext } from '@/app/context';
import { ComparisonBar, TrendChart } from '@/components/charts';
import { Card, ErrorBanner, LoadingBlock } from '@/components/ui';

/** Trend across periods + comparison across entities for one metric. Chart clicks drill down to the metric detail. */
export function MetricExplorer({ code }: { code: string }) {
  const { scope, period, setEntity } = useAppContext();
  const navigate = useNavigate();
  const detail = useMetricDetail(code, scope);
  const cmp = useEntityComparison(code, period);
  const d = detail.data;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Card title={`Trend · ${d?.metric.name ?? code}`} subtitle={d ? `${d.entity.code} · ${d.metric.unit ?? 'no unit'}` : undefined} actions={<button type="button" className="btn-secondary btn-sm" onClick={() => navigate(`/metrics/${encodeURIComponent(code)}`)}>Open metric</button>}>
        {detail.isLoading ? (
          <LoadingBlock />
        ) : detail.error ? (
          <ErrorBanner error={detail.error} />
        ) : (
          <TrendChart
            data={(d?.series ?? []).map((s) => ({ label: s.period, value: s.value, meta: { status: s.status } }))}
            unit={d?.metric.unit}
            height={200}
            target={d?.targets?.[0]?.target_value ?? null}
            onPointClick={() => navigate(`/metrics/${encodeURIComponent(code)}`)}
          />
        )}
      </Card>
      <Card title="Entity comparison" subtitle={cmp.data ? `${cmp.data.period}${cmp.data.previous_period ? ` vs ${cmp.data.previous_period}` : ''}` : undefined}>
        {cmp.isLoading ? (
          <LoadingBlock />
        ) : cmp.error ? (
          <ErrorBanner error={cmp.error} />
        ) : (
          <ComparisonBar
            data={(cmp.data?.entities ?? []).map((e) => ({ key: e.entity, label: e.entity, value: e.value, previous: e.previous, meta: { name: e.name, consolidation: e.consolidation } }))}
            unit={cmp.data?.metric.unit}
            currentLabel={cmp.data?.period}
            previousLabel={cmp.data?.previous_period ?? 'Previous'}
            onBarClick={(row) => {
              setEntity(row.key);
              navigate(`/metrics/${encodeURIComponent(code)}`);
            }}
          />
        )}
      </Card>
    </div>
  );
}
