import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useEvidenceGaps } from '@/api/evidence';
import { useCoverages, useFrameworks, useSelectedFrameworks } from '@/api/frameworks';
import { createReport, generateDraft, useTemplates, validateReport } from '@/api/reports';
import type { ReportDetail, ValidationResult } from '@/api/types';
import { useAppContext } from '@/app/context';
import { Card, EmptyState, ErrorBanner, Field, Input, LoadingBlock, Select, SeverityBadge, StatCard, StatusBadge } from '@/components/ui';
import { fmtNumber, titleCase } from '@/lib/format';
import { cn } from '@/lib/utils';
import { PageHeader } from '@/components/ui';

const STEPS = ['Period', 'Organization', 'Frameworks', 'Template', 'Required disclosures', 'Missing data & evidence', 'Create & generate'];

export function ValidationChecks({ v }: { v: ValidationResult }) {
  return (
    <div className="space-y-2">
      <div className={cn('text-sm font-semibold', v.blocked ? 'text-[#8F2C22]' : 'text-[#1F7A3A]')}>{v.blocked ? 'Blocked — critical checks failed' : 'Not blocked'} · {v.checks.filter((c) => c.passed).length}/{v.checks.length} checks passed</div>
      <ul className="space-y-1">
        {v.checks.map((c) => (
          <li key={c.check} className="flex items-start gap-2 text-xs">
            <StatusBadge status={c.passed ? 'passed' : 'failed'} label={c.passed ? 'Pass' : 'Fail'} />
            <span className="min-w-0"><span className="font-medium">{titleCase(c.check)}</span>{!c.passed && <SeverityBadge severity={c.severity} className="ml-1" />}<span className="block text-gray-600 break-words">{c.detail}</span></span>
          </li>
        ))}
      </ul>
      {v.reason.length > 0 && <div className="text-xs"><div className="label">Blocked reason</div><ul className="list-disc pl-5 text-[#8F2C22]">{v.reason.map((r, i) => <li key={i}>{r}</li>)}</ul></div>}
      {v.required_action.length > 0 && <div className="text-xs"><div className="label">Required action</div><ul className="list-disc pl-5 font-medium">{v.required_action.map((r, i) => <li key={i}>{r}</li>)}</ul></div>}
      {v.governance.length > 0 && <div className="text-xs"><div className="label">Governance outcomes</div><ul className="space-y-1">{v.governance.map((g, i) => <li key={i} className="flex items-start gap-2"><SeverityBadge severity={g.severity} /><span><span className="font-mono">{g.rule}</span> · {g.action}: {g.message}{g.required_action && <span className="block text-[#8F2C22]">→ {g.required_action}</span>}</span></li>)}</ul></div>}
    </div>
  );
}

export function ReportBuilderPage() {
  const { org, periods, period: ctxPeriod } = useAppContext();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [period, setPeriod] = useState(ctxPeriod);
  const [frameworks, setFrameworks] = useState<string[]>([]);
  const [template, setTemplate] = useState('ESG_ANNUAL');
  const [title, setTitle] = useState('');
  const fws = useFrameworks();
  const selected = useSelectedFrameworks(period);
  const templates = useTemplates();
  const coverages = useCoverages(step >= 4 ? frameworks : [], period);
  const gaps = useEvidenceGaps(period);
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);

  useEffect(() => {
    if (selected.data && frameworks.length === 0) {
      const codes = selected.data.frameworks.map((f) => f.framework_code);
      setFrameworks(codes.length ? codes : ['WEF_SCM', 'UNGC', 'UN_SDG'].filter((c) => fws.data?.some((f) => f.code === c)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected.data, fws.data]);

  const create = useMutation({ mutationFn: () => createReport({ period_code: period, template_code: template, title: title || null, framework_codes: frameworks }), onSuccess: setReport });
  const draft = useMutation({ mutationFn: () => generateDraft((report as ReportDetail).id), onSuccess: setReport });
  const validate = useMutation({ mutationFn: () => validateReport((report as ReportDetail).id), onSuccess: setValidation });

  const toggleFw = (code: string) => setFrameworks((f) => (f.includes(code) ? f.filter((x) => x !== code) : [...f, code]));
  const canNext = [!!period, !!org, frameworks.length > 0, !!template, true, true, false][step];
  const tpl = templates.data?.find((t) => t.code === template);

  return (
    <div className="space-y-4">
      <PageHeader title="Report Builder" description="Assemble a governed report: period → organization → frameworks → template → required disclosures → gaps → create, draft, validate." showScope={false} />
      <ol className="flex flex-wrap items-center gap-1 text-xs">
        {STEPS.map((s, i) => (
          <li key={s} className="flex items-center gap-1">
            <button type="button" onClick={() => i < step && !report && setStep(i)} className={cn('inline-flex items-center gap-1 rounded px-2 py-1 border', i === step ? 'bg-navy text-white border-navy' : i < step ? 'bg-teal-50 text-teal border-teal-100' : 'bg-white text-gray-500 border-gray-200')}>
              <span className="w-4 h-4 rounded-full bg-white/20 inline-flex items-center justify-center text-[10px]">{i < step ? <Check size={10} /> : i + 1}</span>
              {s}
            </button>
            {i < STEPS.length - 1 && <ChevronRight size={12} className="text-gray-300" />}
          </li>
        ))}
      </ol>

      <Card>
        {step === 0 && (
          <div className="max-w-md space-y-3">
            <Field label="Reporting period" required><Select value={period} onChange={(e) => setPeriod(e.target.value)}>{periods.map((p) => <option key={p.code} value={p.code}>{p.code} · {p.label} ({p.status})</option>)}</Select></Field>
            <p className="text-xs text-gray-600">Metric values, evidence and framework coverage are evaluated for this period.</p>
          </div>
        )}
        {step === 1 && org && (
          <dl className="kv max-w-2xl">
            <dt>Organization</dt><dd className="font-medium">{org.name} ({org.code})</dd>
            <dt>Legal name</dt><dd>{org.legal_name ?? '—'}</dd>
            <dt>Sector</dt><dd>{org.sector ?? '—'}</dd>
            <dt>Headquarters</dt><dd>{org.headquarters ?? '—'}</dd>
            <dt>Reporting boundary</dt><dd>{org.reporting_boundary ?? '—'}</dd>
            <dt>Entities in scope</dt><dd>{org.entities.length} group node(s); consolidation per entity method</dd>
          </dl>
        )}
        {step === 2 && (
          <div className="space-y-2">
            <p className="text-xs text-gray-600">Select the frameworks the report will disclose against. Frameworks already selected for {period} are pre-ticked.</p>
            {fws.isLoading ? <LoadingBlock /> : (
              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                {(fws.data ?? []).map((f) => (
                  <label key={f.code} className={cn('flex items-start gap-2 border rounded p-2 cursor-pointer', frameworks.includes(f.code) ? 'border-teal bg-teal-50' : 'border-gray-200')}>
                    <input type="checkbox" checked={frameworks.includes(f.code)} onChange={() => toggleFw(f.code)} className="mt-0.5" />
                    <span className="text-xs"><span className="font-medium text-navy">{f.code}</span> · {f.name}<span className="block text-gray-500">v{f.current_version ?? '—'} · {f.requirement_count} requirements</span></span>
                  </label>
                ))}
              </div>
            )}
          </div>
        )}
        {step === 3 && (
          <div className="space-y-3">
            <div className="grid gap-2 md:grid-cols-2">
              {(templates.data ?? []).map((t) => (
                <label key={t.code} className={cn('border rounded p-3 cursor-pointer', template === t.code ? 'border-teal bg-teal-50' : 'border-gray-200')}>
                  <input type="radio" name="template" checked={template === t.code} onChange={() => setTemplate(t.code)} className="mr-2" />
                  <span className="font-medium text-navy">{t.name}</span> <span className="font-mono text-xs text-gray-500">{t.code}</span>
                  <p className="text-xs text-gray-600 mt-1">{t.description}</p>
                  <p className="text-xxs text-gray-500 mt-1">{t.sections.length} sections · {t.sections.filter((s) => s.source === 'ai').length} AI-drafted</p>
                </label>
              ))}
            </div>
            <Field label="Report title (optional)"><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={`${org?.name ?? ''} Sustainability Report ${period}`} /></Field>
            {tpl && (
              <details><summary className="text-xs text-teal cursor-pointer">Section outline</summary>
                <ol className="text-xs mt-1 space-y-0.5">{tpl.sections.map((s) => <li key={s.code} className={s.level >= 2 ? 'pl-4' : 'font-medium'}>{s.title} <span className="text-gray-400">· {s.source}{s.metrics?.length ? ` · ${s.metrics.length} metrics` : ''}{s.requirements?.length ? ` · ${s.requirements.length} disclosures` : ''}</span></li>)}</ol>
              </details>
            )}
          </div>
        )}
        {step === 4 && (
          <div className="space-y-3">
            <p className="text-xs text-gray-600">Requirement-level status per selected framework for {period}. Alignment is an internal readiness indicator, not a compliance certification.</p>
            {coverages.map((c, i) => (
              <div key={frameworks[i]} className="border border-gray-200 rounded p-3">
                {c.isLoading ? <LoadingBlock lines={2} /> : c.error ? <ErrorBanner error={c.error} /> : c.data ? (
                  <>
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <span className="font-medium text-navy">{c.data.framework_name ?? frameworks[i]} <span className="text-gray-400 font-normal">v{c.data.version}</span></span>
                      <span className="text-xs">alignment <span className="font-semibold">{fmtNumber(c.data.alignment_pct, { decimals: 1 })}%</span> · {c.data.completed} complete · {c.data.partial} partial · <span className="text-[#8F2C22]">{c.data.missing} missing</span> · {c.data.omitted} omitted</span>
                    </div>
                    <ul className="mt-2 grid gap-1 md:grid-cols-2 text-xs max-h-56 overflow-y-auto">
                      {c.data.requirements.filter((r) => r.status !== 'complete').slice(0, 60).map((r) => (
                        <li key={r.code} className="flex items-center gap-2"><StatusBadge status={r.status} /><span className="font-mono text-gray-600">{r.code}</span><span className="truncate">{r.title}</span></li>
                      ))}
                    </ul>
                    {c.data.disclaimer && <p className="text-xxs text-gray-500 mt-2">{c.data.disclaimer}</p>}
                  </>
                ) : null}
              </div>
            ))}
            {frameworks.length === 0 && <EmptyState compact title="No frameworks selected" />}
          </div>
        )}
        {step === 5 && (
          <div className="space-y-3">
            {gaps.isLoading ? <LoadingBlock /> : gaps.error ? <ErrorBanner error={gaps.error} /> : gaps.data ? (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <StatCard label="Evidence coverage" value={`${fmtNumber(gaps.data.coverage_pct, { decimals: 1 })}%`} />
                  <StatCard label="Values without evidence" value={gaps.data.gaps.length} tone={gaps.data.gaps.length ? 'text-[#8F2C22]' : 'text-[#1F7A3A]'} />
                  <StatCard label="Unverified evidence" value={gaps.data.unverified_evidence} />
                  <StatCard label="Open evidence issues" value={gaps.data.open_issues.length} />
                </div>
                {gaps.data.gaps.length > 0 && (
                  <ul className="grid gap-1 md:grid-cols-2 text-xs max-h-64 overflow-y-auto">
                    {gaps.data.gaps.map((g) => <li key={`${g.metric_code}-${g.entity}`} className="flex items-center gap-2"><SeverityBadge severity={g.severity} /><Link to={`/metrics/${encodeURIComponent(g.metric_code)}`} className="font-mono text-teal">{g.metric_code}</Link><span className="truncate">{g.metric_name}</span><span className="text-gray-400">{g.entity}</span></li>)}
                  </ul>
                )}
                <p className="text-xs text-gray-600">KPI values without evidence will fail the evidence validation check and may block final generation. You can still create the draft and resolve gaps during review.</p>
              </>
            ) : null}
          </div>
        )}
        {step === 6 && (
          <div className="space-y-4">
            <dl className="kv max-w-2xl">
              <dt>Period</dt><dd>{period}</dd>
              <dt>Organization</dt><dd>{org?.name}</dd>
              <dt>Frameworks</dt><dd>{frameworks.join(', ')}</dd>
              <dt>Template</dt><dd>{tpl?.name ?? template}</dd>
              <dt>Title</dt><dd>{title || <span className="text-gray-400">default</span>}</dd>
            </dl>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className="btn-primary" onClick={() => create.mutate()} disabled={create.isPending || !!report}>{report ? <><Check size={14} /> Report #{report.id} created</> : create.isPending ? 'Creating…' : '1. Create report'}</button>
              <button type="button" className="btn-primary" onClick={() => draft.mutate()} disabled={!report || draft.isPending}>{draft.isPending ? 'Generating draft…' : '2. Generate draft (AI + data)'}</button>
              <button type="button" className="btn-primary" onClick={() => validate.mutate()} disabled={!report || validate.isPending}>{validate.isPending ? 'Validating…' : '3. Validate (9 checks)'}</button>
              {report && <button type="button" className="btn-accent" onClick={() => navigate(`/reports/${report.id}/preview`)}>4. Open preview →</button>}
            </div>
            {create.error ? <ErrorBanner error={create.error} /> : null}
            {draft.error ? <ErrorBanner error={draft.error} /> : null}
            {validate.error ? <ErrorBanner error={validate.error} /> : null}
            {report && (
              <div className="border border-gray-200 rounded p-3 text-xs">
                <div className="flex items-center gap-2"><span className="font-medium text-navy">{report.title}</span><StatusBadge status={report.status} /><span className="text-gray-500">{report.sections.length} sections</span></div>
                <ul className="mt-2 grid gap-1 md:grid-cols-3">{report.sections.map((s) => <li key={s.code} className="flex items-center gap-2"><StatusBadge status={s.status} /><span className={s.level >= 2 ? 'pl-2' : 'font-medium'}>{s.title}</span></li>)}</ul>
              </div>
            )}
            {validation && <div className="border border-gray-200 rounded p-3"><ValidationChecks v={validation} /></div>}
          </div>
        )}
      </Card>

      <div className="flex items-center justify-between">
        <button type="button" className="btn-secondary" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0 || !!report}><ChevronLeft size={14} /> Back</button>
        {step < STEPS.length - 1 && <button type="button" className="btn-primary" onClick={() => setStep((s) => s + 1)} disabled={!canNext}>Next <ChevronRight size={14} /></button>}
      </div>
    </div>
  );
}
