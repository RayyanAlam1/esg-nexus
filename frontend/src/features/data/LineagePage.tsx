import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useLineage } from '@/api/datasets';
import { useMetrics } from '@/api/metrics';
import { useAppContext } from '@/app/context';
import { LineageGraphView } from '@/components/charts';
import { Card, EmptyState, ErrorBanner, Field, Input, LoadingBlock, PageHeader, Select } from '@/components/ui';
import { useDebounce } from '@/lib/utils';

export function LineagePage() {
  const { periods, entities, period, entity } = useAppContext();
  const [params, setParams] = useSearchParams();
  const metric = params.get('metric') ?? '';
  const [p, setP] = useState(params.get('period') ?? period);
  const [e, setE] = useState(params.get('entity') ?? entity);
  const [search, setSearch] = useState('');
  const ds = useDebounce(search, 300);
  const options = useMetrics({ q: ds || undefined, limit: 30, kpi: ds ? undefined : true });
  const lineage = useLineage(metric || null, { period: p, entity: e });

  const setMetric = (code: string) => {
    const np = new URLSearchParams(params);
    if (code) np.set('metric', code);
    else np.delete('metric');
    setParams(np, { replace: true });
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Data Lineage" description="Trace any reported number: metric → calculation → inputs → dataset → source → evidence. Select a metric, entity and period." showScope={false} />
      <Card bodyClassName="p-3">
        <div className="grid gap-3 md:grid-cols-4">
          <Field label="Search metric">
            <Input value={search} onChange={(ev) => setSearch(ev.target.value)} placeholder="Type to search (KPIs shown by default)" />
          </Field>
          <Field label="Metric">
            <Select value={metric} onChange={(ev) => setMetric(ev.target.value)}>
              <option value="">Select a metric…</option>
              {metric && !options.data?.items.some((m) => m.code === metric) && <option value={metric}>{metric}</option>}
              {(options.data?.items ?? []).map((m) => (
                <option key={m.code} value={m.code}>{m.code} · {m.name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Entity">
            <Select value={e} onChange={(ev) => setE(ev.target.value)}>
              {entities.map((x) => (
                <option key={x.code} value={x.code}>{x.code} · {x.name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Period">
            <Select value={p} onChange={(ev) => setP(ev.target.value)}>
              {periods.map((x) => (
                <option key={x.code} value={x.code}>{x.code}</option>
              ))}
            </Select>
          </Field>
        </div>
      </Card>
      {!metric ? (
        <EmptyState title="Select a metric to trace its lineage" />
      ) : lineage.isLoading ? (
        <LoadingBlock lines={6} />
      ) : lineage.error ? (
        <ErrorBanner error={lineage.error} />
      ) : (
        <>
          <Card title="Lineage chain">
            {lineage.data?.chain.length ? (
              <ol className="text-[13px] space-y-1 font-mono">
                {lineage.data.chain.map((c, i) => (
                  <li key={i} className={i === 0 ? 'font-semibold text-navy' : 'pl-4 text-gray-700'}>{c}</li>
                ))}
              </ol>
            ) : (
              <EmptyState compact title="Data unavailable" hint="No value is recorded for this metric, entity and period." />
            )}
          </Card>
          <Card title="Lineage graph">
            <LineageGraphView graph={lineage.data?.graph} height={520} />
          </Card>
        </>
      )}
    </div>
  );
}
