import { useState } from 'react';
import { ArrowRight, CheckCircle2, XCircle } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useOverview } from '@/api/esg';
import type { Issue, Readiness } from '@/api/types';
import { useAppContext } from '@/app/context';
import { Card, DataTable, DimensionBars, EmptyState, ErrorBanner, KpiCard, LoadingBlock, Modal, PageHeader, ScoreRing, SeverityBadge, StatCard, StatusBadge, type Column } from '@/components/ui';
import { SEVERITY_ORDER } from '@/lib/colors';
import { fmtNumber, fmtPct, titleCase } from '@/lib/format';
import { cn } from '@/lib/utils';

const COMPONENT_LABELS: Record<string, string> = {
  data_completeness: 'Data completeness',
  data_quality: 'Data quality',
  evidence_coverage: 'Evidence coverage',
  framework_alignment: 'Framework alignment',
  governance_checks: 'Governance checks',
  ai_evaluation: 'AI evaluation',
  human_approvals: 'Human approvals',
};

export function ReadinessPanel({ readiness, period }: { readiness: Readiness; period: string }) {
  const [open, setOpen] = useState(false);
  const components = Object.keys(COMPONENT_LABELS).map((k) => ({ key: k, label: COMPONENT_LABELS[k], value: readiness.components[k] ?? null }));
  return (
    <Card title="Report Readiness" subtitle={`Weighted blend of 7 components · ${period}`} actions={<button type="button" className="btn-secondary btn-sm" onClick={() => setOpen(true)}>Explain</button>}>
      <div className="grid gap-4 md:grid-cols-[150px_1fr]">
        <div className="flex flex-col items-center gap-2">
          <ScoreRing value={readiness.overall} label="Overall" onClick={() => setOpen(true)} />
          <div className={cn('inline-flex items-center gap-1 text-xs font-medium', readiness.ready_to_publish ? 'text-[#1F7A3A]' : 'text-[#8F2C22]')}>
            {readiness.ready_to_publish ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
            {readiness.ready_to_publish ? 'Ready to publish' : 'Not ready to publish'}
          </div>
        </div>
        <DimensionBars data={components} onClick={() => setOpen(true)} labelWidth={160} />
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title="Readiness explanation" width="max-w-2xl">
        <ul className="list-disc pl-5 text-[13px] space-y-1">
          {readiness.explanation.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mt-4 mb-1">Blocking issues ({readiness.blocking_issues.length})</h4>
        {readiness.blocking_issues.length === 0 ? (
          <p className="text-xs text-gray-600">No blocking issues. {readiness.overall < 80 ? 'Readiness must reach 80% before publication.' : ''}</p>
        ) : (
          <ul className="space-y-1.5">
            {readiness.blocking_issues.map((b) => (
              <li key={b.code} className="text-xs border border-gray-200 rounded p-2">
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={b.severity} />
                  <span className="font-mono text-gray-500">{b.code}</span>
                  {b.metric_code && (
                    <Link to={`/metrics/${encodeURIComponent(b.metric_code)}`} className="text-teal font-mono">
                      {b.metric_code}
                    </Link>
                  )}
                </div>
                <div className="font-medium mt-1">{b.title}</div>
                {b.required_action && <div className="text-[#8F2C22]">Required: {b.required_action}</div>}
              </li>
            ))}
          </ul>
        )}
        <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mt-4 mb-1">Open issues by severity</h4>
        <div className="flex gap-3 text-xs">
          {SEVERITY_ORDER.map((s) => (
            <span key={s} className="inline-flex items-center gap-1">
              <SeverityBadge severity={s} /> {readiness.open_issues[s] ?? 0}
            </span>
          ))}
        </div>
      </Modal>
    </Card>
  );
}

export function DashboardPage() {
  const { scope, period } = useAppContext();
  const navigate = useNavigate();
  const q = useOverview(scope);

  if (q.isLoading) return <LoadingBlock lines={8} />;
  if (q.error) return <ErrorBanner error={q.error} />;
  const d = q.data;
  if (!d) return <EmptyState />;

  const issueCols: Column<Issue>[] = [
    { key: 'severity', header: 'Severity', render: (i) => <SeverityBadge severity={i.severity} />, width: '90px' },
    { key: 'title', header: 'Issue', render: (i) => <span className="font-medium">{i.title}</span> },
    { key: 'category', header: 'Category', render: (i) => titleCase(i.category) },
    {
      key: 'metric_code',
      header: 'Metric',
      render: (i) =>
        i.metric_code ? (
          <Link to={`/metrics/${encodeURIComponent(i.metric_code)}`} className="font-mono text-xs text-teal" onClick={(e) => e.stopPropagation()}>
            {i.metric_code}
          </Link>
        ) : (
          '—'
        ),
    },
    { key: 'entity_code', header: 'Entity', render: (i) => i.entity_code ?? '—' },
    { key: 'status', header: 'Status', render: (i) => <StatusBadge status={i.status} /> },
    { key: 'blocks', header: 'Blocks report', render: (i) => (i.blocks_report ? <span className="text-[#8F2C22] font-medium">Yes</span> : 'No') },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title="Executive Dashboard" description={`${d.organization.name} · ${d.period.label} · ${d.entity.name}. ${d.coverage.values_in_period.toLocaleString()} values recorded across ${d.coverage.metric_definitions.toLocaleString()} metric definitions.`} />

      <section>
        <div className="section-q">Are we ready to publish?</div>
        <ReadinessPanel readiness={d.readiness} period={period} />
      </section>

      <section>
        <div className="section-q">What is happening?</div>
        <div className="grid gap-3 grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
          {d.kpis.map((k) => (
            <KpiCard key={k.code} kpi={k} />
          ))}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section>
          <div className="section-q">What changed?</div>
          <Card title="Movements ≥ 5% year on year" subtitle={`${period} vs previous period`} bodyClassName="p-0">
            {d.what_changed.length === 0 ? (
              <EmptyState compact title="No material movements" hint="No KPI moved by 5% or more, or prior-period data is unavailable." />
            ) : (
              <ul>
                {d.what_changed.map((k) => (
                  <li key={k.code}>
                    <button type="button" className="w-full flex items-center justify-between gap-3 px-4 py-2 border-b border-gray-100 hover:bg-navy-50/60 text-left" onClick={() => navigate(`/metrics/${encodeURIComponent(k.code)}`)}>
                      <span className="min-w-0">
                        <span className="block text-[13px] font-medium truncate">{k.name}</span>
                        <span className="block text-xs text-gray-500 tabular-nums">
                          {fmtNumber(k.previous)} → {fmtNumber(k.value)} {k.unit ?? ''}
                        </span>
                      </span>
                      <span className={cn('text-sm font-semibold tabular-nums whitespace-nowrap', k.trend === 'improving' ? 'text-[#1F7A3A]' : k.trend === 'worsening' ? 'text-[#8F2C22]' : 'text-gray-700')}>{fmtPct(k.yoy_pct)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </section>

        <section>
          <div className="section-q">What is missing?</div>
          <Card title="Gaps affecting readiness">
            <div className="grid grid-cols-2 gap-2">
              <StatCard label="Data completeness" value={`${fmtNumber(d.readiness.components.data_completeness, { decimals: 1 })}%`} hint="KPIs with values" onClick={() => navigate('/metrics/kpis')} />
              <StatCard label="Evidence coverage" value={`${fmtNumber(d.readiness.components.evidence_coverage, { decimals: 1 })}%`} hint="Values linked to evidence" onClick={() => navigate('/evidence/gaps')} />
              <StatCard label="Framework alignment" value={`${fmtNumber(d.readiness.components.framework_alignment, { decimals: 1 })}%`} hint="WEF SCM · UNGC · UN SDG" onClick={() => navigate('/standards/compliance')} />
              <StatCard label="Blocking issues" value={d.readiness.blocking_issues.length} tone={d.readiness.blocking_issues.length ? 'text-[#8F2C22]' : 'text-[#1F7A3A]'} hint="Must be resolved or excepted" onClick={() => navigate('/governance/issues')} />
            </div>
            {d.readiness.blocking_issues.length > 0 && (
              <ul className="mt-3 space-y-1 text-xs">
                {d.readiness.blocking_issues.slice(0, 5).map((b) => (
                  <li key={b.code} className="flex items-start gap-2">
                    <SeverityBadge severity={b.severity} />
                    <span>
                      {b.title}
                      {b.required_action && <span className="block text-[#8F2C22]">→ {b.required_action}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </section>
      </div>

      <section>
        <div className="section-q">Where are the risks?</div>
        <div className="grid gap-3 grid-cols-2 md:grid-cols-4 mb-3">
          <StatCard label="Open issues" value={d.issues.total} onClick={() => navigate('/governance/issues')} />
          <StatCard label="Critical" value={d.issues.critical} tone={d.issues.critical ? 'text-[#8F2C22]' : 'text-navy'} onClick={() => navigate('/governance/issues?severity=CRITICAL')} />
          <StatCard label="High" value={d.issues.high} tone={d.issues.high ? 'text-[#9A5A17]' : 'text-navy'} onClick={() => navigate('/governance/issues?severity=HIGH')} />
          <StatCard label="Governance score" value={`${fmtNumber(d.readiness.components.governance_checks, { decimals: 1 })}%`} hint="100 − severity penalties" onClick={() => navigate('/governance/rules')} />
        </div>
        <Card
          title="Top open issues"
          bodyClassName="p-0"
          actions={
            <Link to="/governance/issues" className="text-xs text-teal inline-flex items-center gap-1">
              All issues <ArrowRight size={12} />
            </Link>
          }
        >
          <DataTable columns={issueCols} rows={d.issues.top} rowKey={(i) => i.id} onRowClick={(i) => navigate(`/governance/issues?q=${encodeURIComponent(i.code)}`)} emptyTitle="No open issues" dense />
        </Card>
      </section>
    </div>
  );
}
