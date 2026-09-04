import { Fragment, useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Sparkles } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { gapAnalysis, useCoverage, useFrameworks, useSelectedFrameworks } from '@/api/frameworks';
import type { AgentResult, RequirementStatus } from '@/api/types';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { Card, EmptyState, ErrorBanner, Input, LoadingBlock, PageHeader, ScoreRing, Select, StatCard, StatusBadge } from '@/components/ui';
import { titleCase } from '@/lib/format';
import { cn } from '@/lib/utils';
import { AgentResultView } from '../ai/AgentResultView';

function GapFlag({ on, label }: { on: boolean; label: string }) {
  return <span className={cn('badge', on ? 'bg-red-50 text-[#8F2C22] border-red-200' : 'bg-gray-50 text-gray-400 border-gray-200')}>{label}</span>;
}

export function CompliancePage() {
  const { period } = useAppContext();
  const { hasCap } = useAuth();
  const [params, setParams] = useSearchParams();
  const fws = useFrameworks();
  const selected = useSelectedFrameworks(period);
  const framework = params.get('framework') ?? '';
  const [q, setQ] = useState(params.get('q') ?? '');
  const [status, setStatus] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [analysis, setAnalysis] = useState<AgentResult | null>(null);

  useEffect(() => {
    if (!framework && (selected.data?.frameworks.length || fws.data?.length)) {
      const def = selected.data?.frameworks[0]?.framework_code ?? fws.data?.find((f) => f.code === 'WEF_SCM')?.code ?? fws.data?.[0]?.code;
      if (def) setParams({ framework: def }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected.data, fws.data]);

  const cov = useCoverage(framework || null, period);
  const gap = useMutation({ mutationFn: () => gapAnalysis(framework, period), onSuccess: setAnalysis });

  const rows = (cov.data?.requirements ?? []).filter((r) => (!status || r.status === status) && (!q || `${r.code} ${r.title} ${r.theme ?? ''}`.toLowerCase().includes(q.toLowerCase())));
  const toggle = (code: string) =>
    setExpanded((s) => {
      const n = new Set(s);
      if (n.has(code)) n.delete(code);
      else n.add(code);
      return n;
    });

  return (
    <div className="space-y-4">
      <PageHeader
        title="Compliance · Framework Alignment"
        description="Requirement-level readiness for the selected framework and period. Alignment is an internal indicator of disclosure coverage — it is not a compliance certification."
        actions={
          <>
            <Select value={framework} onChange={(e) => { setParams({ framework: e.target.value }, { replace: true }); setAnalysis(null); }} className="w-72" aria-label="Framework">
              {(fws.data ?? []).map((f) => (
                <option key={f.code} value={f.code}>{f.code} · {f.name}</option>
              ))}
            </Select>
            {hasCap('ai.run') && (
              <button type="button" className="btn-accent" onClick={() => gap.mutate()} disabled={!framework || gap.isPending}>
                <Sparkles size={14} /> {gap.isPending ? 'Analysing…' : 'Run gap analysis (AI)'}
              </button>
            )}
          </>
        }
      />
      {gap.error ? <ErrorBanner error={gap.error} /> : null}
      {cov.isLoading ? (
        <LoadingBlock lines={6} />
      ) : cov.error ? (
        <ErrorBanner error={cov.error} />
      ) : cov.data ? (
        <>
          {cov.data.error && <ErrorBanner error={new Error(cov.data.error)} />}
          <div className="grid gap-3 md:grid-cols-[180px_1fr]">
            <Card bodyClassName="flex items-center justify-center p-3">
              <ScoreRing value={cov.data.alignment_pct} label="Alignment" sublabel={`${cov.data.framework_name ?? framework} v${cov.data.version ?? '—'}`} />
            </Card>
            <div className="grid gap-2 grid-cols-2 md:grid-cols-4 xl:grid-cols-8">
              <StatCard label="Applicable" value={cov.data.applicable ?? 0} />
              <StatCard label="Complete" value={cov.data.completed ?? 0} tone="text-[#1F7A3A]" onClick={() => setStatus('complete')} />
              <StatCard label="Partial" value={cov.data.partial ?? 0} tone="text-[#7A6215]" onClick={() => setStatus('partial')} />
              <StatCard label="Missing" value={cov.data.missing ?? 0} tone="text-[#8F2C22]" onClick={() => setStatus('missing')} />
              <StatCard label="Omitted" value={cov.data.omitted ?? 0} onClick={() => setStatus('omitted')} />
              <StatCard label="Evidence gaps" value={cov.data.evidence_gaps ?? 0} tone="text-[#9A5A17]" />
              <StatCard label="Metric gaps" value={cov.data.metric_gaps ?? 0} tone="text-[#9A5A17]" />
              <StatCard label="Narrative gaps" value={cov.data.narrative_gaps ?? 0} tone="text-[#9A5A17]" />
            </div>
          </div>
          {cov.data.disclaimer && <p className="text-xs text-gray-600 border-l-2 border-[#C9A227] pl-2">{cov.data.disclaimer}</p>}
          {analysis && (
            <Card title="Gap analysis (Standards Mapping Agent)" actions={<button type="button" className="btn-ghost btn-sm" onClick={() => setAnalysis(null)}>Dismiss</button>}>
              <AgentResultView r={analysis} />
              <p className="text-xxs text-gray-500 mt-2">AI gap analysis is advisory and grounded in registry requirements and governed metrics; it does not constitute a compliance opinion.</p>
            </Card>
          )}
          <Card
            title={`Requirements · ${rows.length}`}
            bodyClassName="p-0"
            actions={
              <>
                <Input placeholder="Filter…" value={q} onChange={(e) => setQ(e.target.value)} className="w-52" aria-label="Filter requirements" />
                <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-36" aria-label="Status filter">
                  <option value="">All statuses</option>
                  {['complete', 'partial', 'missing', 'omitted'].map((s) => (
                    <option key={s} value={s}>{titleCase(s)}</option>
                  ))}
                </Select>
              </>
            }
          >
            {rows.length === 0 ? (
              <EmptyState compact title="No requirements match" />
            ) : (
              <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr><th className="w-6"></th><th>Code</th><th>Requirement</th><th>Pillar</th><th>Disclosure</th><th>Status</th><th>Gaps</th><th className="text-right">Metrics</th></tr>
                  </thead>
                  <tbody>
                    {rows.map((r: RequirementStatus) => {
                      const isOpen = expanded.has(r.code);
                      return (
                        <Fragment key={r.code}>
                          <tr className="cursor-pointer" onClick={() => toggle(r.code)}>
                            <td>{isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
                            <td className="font-mono text-xs text-navy">{r.code}</td>
                            <td><span className="font-medium">{r.title}</span>{r.theme && <span className="block text-xxs text-gray-500">{r.theme}</span>}</td>
                            <td>{titleCase(r.pillar)}</td>
                            <td>{r.disclosure_type}</td>
                            <td><StatusBadge status={r.status} /></td>
                            <td className="space-x-1"><GapFlag on={r.metric_gap} label="metric" /><GapFlag on={r.evidence_gap} label="evidence" /><GapFlag on={r.narrative_gap} label="narrative" /></td>
                            <td className="text-right">{r.metrics.filter((m) => m.has_value).length}/{r.metrics.length}</td>
                          </tr>
                          {isOpen && (
                            <tr>
                              <td></td>
                              <td colSpan={7} className="bg-gray-50">
                                {r.description && <p className="text-xs text-gray-700 mb-2">{r.description}</p>}
                                {r.guidance && <p className="text-xs text-gray-500 mb-2">Guidance: {r.guidance}</p>}
                                {r.omission_reason && <p className="text-xs text-[#7A6215] mb-2">Omitted: {r.omission_reason}</p>}
                                {r.metrics.length === 0 ? (
                                  <p className="text-xs text-gray-500">No metrics mapped{r.disclosure_type === 'narrative' ? ' (narrative disclosure)' : ''}.</p>
                                ) : (
                                  <table className="table">
                                    <thead><tr><th>Metric</th><th>Name</th><th>Kind</th><th>Value</th><th>Evidence</th></tr></thead>
                                    <tbody>
                                      {r.metrics.map((m) => (
                                        <tr key={m.code}>
                                          <td><Link to={`/metrics/${encodeURIComponent(m.code)}`} className="font-mono text-xs text-teal">{m.code}</Link></td>
                                          <td>{m.name}</td>
                                          <td>{m.kind}</td>
                                          <td><StatusBadge status={m.has_value ? 'complete' : 'missing'} label={m.has_value ? 'Has value' : 'Missing'} /></td>
                                          <td><StatusBadge status={m.has_evidence ? 'verified' : 'unverified'} label={m.has_evidence ? 'Linked' : 'No evidence'} /></td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                )}
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      ) : (
        <EmptyState title="Select a framework" />
      )}
    </div>
  );
}
