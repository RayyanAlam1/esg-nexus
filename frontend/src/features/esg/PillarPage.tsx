import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { usePillar } from '@/api/esg';
import type { PillarTopic } from '@/api/types';
import { useAppContext } from '@/app/context';
import { Card, EmptyState, ErrorBanner, KpiCard, LoadingBlock, PageHeader, Select, Tabs } from '@/components/ui';
import { PILLAR_LABEL } from '@/lib/colors';
import { MetricExplorer } from './MetricExplorer';

const TAB_CONFIG: Record<string, { key: string; label: string; topics: string[] }[]> = {
  environment: [
    { key: 'climate', label: 'Climate', topics: ['climate'] },
    { key: 'energy', label: 'Energy', topics: ['energy'] },
    { key: 'ghg', label: 'GHG', topics: ['ghg_emissions'] },
    { key: 'water', label: 'Water', topics: ['water'] },
    { key: 'waste', label: 'Waste', topics: ['waste'] },
    { key: 'biodiversity', label: 'Biodiversity', topics: ['biodiversity'] },
    { key: 'management', label: 'Management', topics: ['environmental_management'] },
  ],
  social: [
    { key: 'workforce', label: 'Workforce', topics: ['workforce'] },
    { key: 'dei', label: 'DEI', topics: ['diversity_inclusion', 'compensation'] },
    { key: 'talent', label: 'Talent', topics: ['talent_development'] },
    { key: 'ohs', label: 'Health & Safety', topics: ['health_safety'] },
    { key: 'wellbeing', label: 'Wellbeing', topics: ['wellbeing'] },
    { key: 'labour', label: 'Labour & Human Rights', topics: ['labor_practices'] },
    { key: 'community', label: 'Community', topics: ['community_investment'] },
  ],
  governance: [
    { key: 'board', label: 'Board', topics: ['board'] },
    { key: 'ethics', label: 'Ethics', topics: ['ethics_compliance'] },
    { key: 'risk', label: 'Risk', topics: ['risk_management'] },
    { key: 'cyber', label: 'Cyber & Digital', topics: ['cybersecurity', 'digitalization'] },
    { key: 'reporting', label: 'Reporting & Assurance', topics: ['reporting_assurance'] },
    { key: 'memberships', label: 'Memberships', topics: ['memberships'] },
    { key: 'stakeholders', label: 'Stakeholders', topics: ['stakeholder_engagement'] },
  ],
  prosperity: [
    { key: 'economic', label: 'Economic Performance', topics: ['economic_performance'] },
    { key: 'wealth', label: 'Wealth Distribution', topics: ['wealth_distribution'] },
    { key: 'tax', label: 'Tax', topics: ['tax'] },
    { key: 'investment', label: 'Investment', topics: ['investment'] },
    { key: 'business', label: 'Business Units', topics: ['business_performance'] },
    { key: 'innovation', label: 'Innovation', topics: ['innovation'] },
    { key: 'ratings', label: 'Credit Ratings', topics: ['credit_ratings'] },
  ],
};

function TopicSection({ topic, selected, onSelect }: { topic: PillarTopic; selected: string | null; onSelect: (code: string) => void }) {
  return (
    <Card title={topic.name} subtitle={topic.description ?? undefined} actions={<span className="text-xs text-gray-500">{topic.metrics.length} metrics · {topic.kpis.length} KPIs</span>}>
      {topic.metrics.length === 0 && topic.narratives.length === 0 ? (
        <EmptyState compact title="No metrics in this topic" />
      ) : (
        <>
          {topic.metrics.length > 0 && (
            <div className="grid gap-2 grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
              {topic.metrics.map((k) => (
                <div key={k.code} className="relative">
                  <KpiCard kpi={k} />
                  <button
                    type="button"
                    className={`absolute top-1 right-1 text-xxs px-1 rounded bg-white/90 ${selected === k.code ? 'text-navy font-semibold' : 'text-teal hover:underline'}`}
                    onClick={() => onSelect(k.code)}
                    aria-label={`Show trend for ${k.name}`}
                  >
                    Trend
                  </button>
                </div>
              ))}
            </div>
          )}
          {topic.narratives.length > 0 && (
            <div className="mt-3 space-y-2">
              {topic.narratives.map((n) => (
                <div key={n.code} className="border-l-2 border-teal pl-3">
                  <div className="text-xs font-semibold text-navy">
                    {n.name} <span className="font-mono text-gray-400 font-normal">{n.code}</span>
                  </div>
                  {n.data_unavailable || !n.text ? <p className="text-xs text-gray-400 italic">Data unavailable</p> : <p className="text-[13px] text-gray-700 whitespace-pre-line">{n.text}</p>}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </Card>
  );
}

export function PillarPage() {
  const { pillar = 'environment' } = useParams();
  const { scope } = useAppContext();
  const q = usePillar(pillar, scope);
  const tabs = TAB_CONFIG[pillar] ?? [];
  const [tab, setTab] = useState<string>('all');
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    setTab('all');
    setSelected(null);
  }, [pillar]);

  const topics = q.data?.topics ?? [];
  const configured = new Set(tabs.flatMap((t) => t.topics));
  const visible = useMemo(() => {
    if (tab === 'all') return topics;
    if (tab === 'other') return topics.filter((t) => !configured.has(t.code));
    const cfg = tabs.find((t) => t.key === tab);
    return topics.filter((t) => cfg?.topics.includes(t.code));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, topics, pillar]);
  const other = topics.filter((t) => !configured.has(t.code));
  const allMetrics = visible.flatMap((t) => t.metrics);

  useEffect(() => {
    if (!selected || !allMetrics.some((m) => m.code === selected)) {
      const first = allMetrics.find((m) => m.is_kpi) ?? allMetrics[0];
      setSelected(first?.code ?? null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  if (!TAB_CONFIG[pillar]) return <ErrorBanner error={new Error(`Unknown pillar "${pillar}"`)} />;

  return (
    <div className="space-y-4">
      <PageHeader title={PILLAR_LABEL[pillar as keyof typeof PILLAR_LABEL] ?? pillar} description={`Topic-level KPIs, narrative disclosures, trend and entity comparison for the ${pillar} pillar.`} />
      <Tabs
        tabs={[{ key: 'all', label: 'All topics', count: topics.length }, ...tabs.map((t) => ({ key: t.key, label: t.label, count: topics.filter((x) => t.topics.includes(x.code)).length })), ...(other.length ? [{ key: 'other', label: 'Other', count: other.length }] : [])]}
        active={tab}
        onChange={setTab}
      />
      {q.isLoading ? (
        <LoadingBlock lines={8} />
      ) : q.error ? (
        <ErrorBanner error={q.error} />
      ) : (
        <>
          {allMetrics.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="label mb-0">Trend &amp; comparison for</span>
                <Select className="w-auto max-w-md" value={selected ?? ''} onChange={(e) => setSelected(e.target.value)} aria-label="Metric to explore">
                  {allMetrics.map((m) => (
                    <option key={m.code} value={m.code}>
                      {m.name} ({m.code})
                    </option>
                  ))}
                </Select>
              </div>
              {selected && <MetricExplorer code={selected} />}
            </div>
          )}
          {visible.length === 0 ? <EmptyState title="No topics" /> : visible.map((t) => <TopicSection key={t.code} topic={t} selected={selected} onSelect={setSelected} />)}
        </>
      )}
    </div>
  );
}
