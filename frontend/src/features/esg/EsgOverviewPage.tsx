import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useOverview } from '@/api/esg';
import { useKpis } from '@/api/metrics';
import type { Pillar } from '@/api/types';
import { useAppContext } from '@/app/context';
import { Card, EmptyState, ErrorBanner, KpiCard, LoadingBlock, PageHeader, StatCard } from '@/components/ui';
import { PILLAR_HEX, PILLAR_LABEL } from '@/lib/colors';
import { fmtNumber } from '@/lib/format';
import { ReadinessPanel } from '../dashboard/DashboardPage';
import { MetricExplorer } from './MetricExplorer';

const PILLARS: Pillar[] = ['environment', 'social', 'governance', 'prosperity'];

export function EsgOverviewPage() {
  const { scope, period } = useAppContext();
  const overview = useOverview(scope);
  const kpis = useKpis(scope);
  const [explore, setExplore] = useState<string | null>(null);

  if (kpis.isLoading || overview.isLoading) return <LoadingBlock lines={8} />;
  if (kpis.error) return <ErrorBanner error={kpis.error} />;
  const all = kpis.data?.kpis ?? [];

  return (
    <div className="space-y-4">
      <PageHeader title="ESG Overview" description="All KPIs by pillar with year-on-year movement, target status, evidence and quality. Click a card to open the metric; use Explore to see trend and entity comparison." />
      {overview.data && <ReadinessPanel readiness={overview.data.readiness} period={period} />}
      <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
        {PILLARS.map((p) => {
          const list = all.filter((k) => k.pillar === p);
          const available = list.filter((k) => k.value !== null).length;
          const worsening = list.filter((k) => k.trend === 'worsening').length;
          return (
            <StatCard
              key={p}
              label={PILLAR_LABEL[p]}
              value={`${available}/${list.length}`}
              hint={`KPIs with data · ${worsening} worsening`}
              icon={<span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: PILLAR_HEX[p] }} aria-hidden="true" />}
            />
          );
        })}
      </div>
      {explore && (
        <Card title="Explore" actions={<button type="button" className="btn-ghost btn-sm" onClick={() => setExplore(null)}>Close</button>} bodyClassName="p-3">
          <MetricExplorer code={explore} />
        </Card>
      )}
      {PILLARS.map((p) => {
        const list = all.filter((k) => k.pillar === p);
        return (
          <Card
            key={p}
            title={
              <span className="inline-flex items-center gap-2">
                <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: PILLAR_HEX[p] }} aria-hidden="true" />
                {PILLAR_LABEL[p]}
              </span>
            }
            subtitle={`${list.length} KPIs · avg quality ${fmtNumber(list.filter((k) => k.quality_score !== null).reduce((a, k, _, arr) => a + (k.quality_score ?? 0) / arr.length, 0) || null, { decimals: 1 })}`}
            actions={
              <Link to={`/esg/${p}`} className="text-xs text-teal">
                Open pillar
              </Link>
            }
          >
            {list.length === 0 ? (
              <EmptyState compact title="No KPIs defined" />
            ) : (
              <div className="grid gap-2 grid-cols-2 md:grid-cols-3 xl:grid-cols-5">
                {list.map((k) => (
                  <div key={k.code} className="relative">
                    <KpiCard kpi={k} compact />
                    <button type="button" className="absolute top-1 right-1 text-xxs text-teal hover:underline bg-white/80 px-1 rounded" onClick={() => setExplore(k.code)} aria-label={`Explore ${k.name}`}>
                      Explore
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
