import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { updateTopic, type TopicScoreIn } from '@/api/materiality';
import type { MaterialityTopic } from '@/api/types';
import { useAuth } from '@/app/auth';
import { Drawer, ErrorBanner, Field, Input, StatusBadge, Textarea } from '@/components/ui';
import { PILLAR_LABEL } from '@/lib/colors';
import { fmtNumber, fmtValue, UNAVAILABLE } from '@/lib/format';

export function TopicPanel({ assessmentId, topic, threshold, onClose }: { assessmentId: number; topic: MaterialityTopic | null; threshold: number; onClose: () => void }) {
  const { hasCap } = useAuth();
  const qc = useQueryClient();
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState<TopicScoreIn>({});
  useEffect(() => {
    if (topic) {
      setForm({ impact_severity: topic.impact_severity, impact_likelihood: topic.impact_likelihood, financial_magnitude: topic.financial_magnitude, financial_likelihood: topic.financial_likelihood, stakeholder_priority: topic.stakeholder_priority, rationale: topic.rationale });
      setEdit(false);
    }
  }, [topic]);
  const save = useMutation({
    mutationFn: () => updateTopic(assessmentId, (topic as MaterialityTopic).topic_code, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['materiality'] });
      setEdit(false);
    },
  });
  if (!topic) return null;
  const num = (k: keyof TopicScoreIn) => (
    <Input type="number" min={1} max={5} step="0.5" value={(form[k] as number | null | undefined) ?? ''} onChange={(e) => setForm({ ...form, [k]: e.target.value === '' ? null : Number(e.target.value) })} />
  );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  return (
    <Drawer
      open={!!topic}
      onClose={onClose}
      title={<span>{topic.name} <span className="text-gray-400 font-normal">· {PILLAR_LABEL[topic.pillar] ?? topic.pillar}</span></span>}
      footer={
        edit ? (
          <>
            <button type="button" className="btn-secondary" onClick={() => setEdit(false)}>Cancel</button>
            <button type="submit" form="topic-form" className="btn-primary" disabled={save.isPending}>Save scores</button>
          </>
        ) : (
          hasCap('metric.write') && <button type="button" className="btn-primary" onClick={() => setEdit(true)}>Edit scores</button>
        )
      }
    >
      <div className="space-y-4 text-[13px]">
        <div className="flex items-center gap-2">
          <StatusBadge status={topic.is_material ? 'complete' : 'draft'} label={topic.is_material ? 'Material' : 'Not material'} />
          <span className="text-xs text-gray-500">threshold {threshold}</span>
        </div>
        {edit ? (
          <form id="topic-form" onSubmit={submit} className="space-y-3">
            {save.error ? <ErrorBanner error={save.error} /> : null}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Impact severity (1–5)">{num('impact_severity')}</Field>
              <Field label="Impact likelihood (1–5)">{num('impact_likelihood')}</Field>
              <Field label="Financial magnitude (1–5)">{num('financial_magnitude')}</Field>
              <Field label="Financial likelihood (1–5)">{num('financial_likelihood')}</Field>
              <Field label="Stakeholder priority (1–5)">{num('stakeholder_priority')}</Field>
            </div>
            <Field label="Rationale">
              <Textarea value={form.rationale ?? ''} onChange={(e) => setForm({ ...form, rationale: e.target.value })} />
            </Field>
            <p className="text-xs text-gray-500">Scores recompute as severity × likelihood / 5; materiality is re-derived from the threshold unless overridden.</p>
          </form>
        ) : (
          <dl className="kv">
            <dt>Impact score</dt><dd className="tabular-nums">{fmtNumber(topic.impact_score, { decimals: 2 })} <span className="text-gray-500">(severity {fmtNumber(topic.impact_severity)} × likelihood {fmtNumber(topic.impact_likelihood)} / 5)</span></dd>
            <dt>Financial score</dt><dd className="tabular-nums">{fmtNumber(topic.financial_score, { decimals: 2 })} <span className="text-gray-500">(magnitude {fmtNumber(topic.financial_magnitude)} × likelihood {fmtNumber(topic.financial_likelihood)} / 5)</span></dd>
            <dt>Stakeholder priority</dt><dd className="tabular-nums">{fmtNumber(topic.stakeholder_priority, { decimals: 1 })}</dd>
            <dt>Rationale</dt><dd>{topic.rationale ?? '—'}</dd>
          </dl>
        )}
        <section>
          <div className="label">Risks</div>
          {topic.risks?.length ? <ul className="list-disc pl-5">{topic.risks.map((r, i) => <li key={i}>{r}</li>)}</ul> : <p className="text-gray-400">None recorded.</p>}
        </section>
        <section>
          <div className="label">Opportunities</div>
          {topic.opportunities?.length ? <ul className="list-disc pl-5">{topic.opportunities.map((r, i) => <li key={i}>{r}</li>)}</ul> : <p className="text-gray-400">None recorded.</p>}
        </section>
        <section>
          <div className="label">Related metrics</div>
          {topic.related_metrics.length === 0 ? (
            <p className="text-gray-400">None.</p>
          ) : (
            <table className="table">
              <thead><tr><th>Metric</th><th>Name</th><th className="text-right">Value</th></tr></thead>
              <tbody>
                {topic.related_metrics.map((m) => (
                  <tr key={m.code}>
                    <td><Link to={`/metrics/${encodeURIComponent(m.code)}`} className="font-mono text-xs text-teal">{m.code}</Link></td>
                    <td>{m.name}</td>
                    <td className="text-right tabular-nums">{m.data_unavailable ? <span className="text-gray-400 italic">{UNAVAILABLE}</span> : fmtValue(m.value, m.unit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        <section>
          <div className="label">Related requirements</div>
          <div className="flex flex-wrap gap-1">{(topic.related_requirement_codes ?? []).map((r) => <span key={r} className="chip font-mono text-xxs">{r}</span>)}{!topic.related_requirement_codes?.length && <span className="text-gray-400">None.</span>}</div>
        </section>
        <section>
          <div className="label">Evidence</div>
          <div className="flex flex-wrap gap-1">{(topic.evidence_codes ?? []).map((e) => <Link key={e} to={`/evidence/${encodeURIComponent(e)}`} className="chip font-mono text-xxs hover:border-teal">{e}</Link>)}{!topic.evidence_codes?.length && <span className="text-gray-400">None.</span>}</div>
        </section>
      </div>
    </Drawer>
  );
}
