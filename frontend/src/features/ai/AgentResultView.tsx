import { Link } from 'react-router-dom';
import type { AgentResult, GuardrailResult } from '@/api/types';
import { ConfidenceBar, DimensionBars, JsonDetails, MarkdownView, Pill, SeverityBadge, StatusBadge } from '@/components/ui';

function Guard({ label, g }: { label: string; g: GuardrailResult | undefined }) {
  if (!g) return null;
  return (
    <div className="text-xs text-gray-700">
      <span className="font-medium">{label}:</span> {g.blocked ? 'blocked' : g.passed ? 'passed' : 'flagged'}
      {g.injection_detected && ' · injection detected'}
      {g.missing_citations && ' · missing citations'}
      {g.unsupported_numbers?.length ? ` · unsupported numbers ${g.unsupported_numbers.join(', ')}` : ''}
      {g.findings?.length ? (
        <ul className="list-disc pl-5 text-gray-600">
          {g.findings.map((f, i) => (
            <li key={i}>{f.message ?? JSON.stringify(f)}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Renders a persisted AgentResult (status, confidence, sources, guardrail, evaluation, governance). */
export function AgentResultView({ r }: { r: AgentResult }) {
  const out = r.output ?? {};
  const answer = (out.answer ?? out.narrative ?? out.summary) as string | undefined;
  const guard = r.guardrail as { input?: GuardrailResult; output?: GuardrailResult; passed?: boolean };
  const rest = Object.fromEntries(Object.entries(out).filter(([k]) => !['answer', 'narrative', 'summary'].includes(k)));
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={r.status} />
        {r.blocked && <span className="badge bg-red-50 text-[#8F2C22] border-red-200">Blocked</span>}
        {r.requires_human_review && <span className="badge bg-amber-50 text-[#7A6215] border-amber-200">Human review required</span>}
        <ConfidenceBar value={r.confidence} />
        <span className="text-xs text-gray-500">
          {r.provider ?? '—'} · {r.latency_ms} ms
          {r.run_id ? (
            <>
              {' · '}
              <Link to={`/ai/runs/${r.run_id}`} className="text-teal">run #{r.run_id}</Link>
            </>
          ) : null}
        </span>
      </div>
      {answer ? <MarkdownView content={answer} /> : null}
      {r.sources?.length > 0 && (
        <div>
          <div className="label">Sources</div>
          <div className="flex flex-wrap gap-1">{r.sources.map((s, i) => <Pill key={i} className="font-mono text-xxs">{s}</Pill>)}</div>
        </div>
      )}
      {r.metrics_used?.length > 0 && (
        <div>
          <div className="label">Metrics used</div>
          <div className="flex flex-wrap gap-1">
            {r.metrics_used.map((m) => (
              <Link key={m} to={`/metrics/${encodeURIComponent(m)}`} className="chip font-mono text-xxs hover:border-teal">{m}</Link>
            ))}
          </div>
        </div>
      )}
      {r.tools_used?.length > 0 && <div className="text-xs text-gray-600">Tools: {r.tools_used.join(', ')}</div>}
      <div className="space-y-1">
        {'input' in guard || 'output' in guard ? (
          <>
            <Guard label="Input guardrail" g={guard.input} />
            <Guard label="Output guardrail" g={guard.output} />
          </>
        ) : (
          <Guard label="Guardrail" g={r.guardrail as unknown as GuardrailResult} />
        )}
      </div>
      {r.evaluation && (
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="label">Evaluation · overall {r.evaluation.overall} ({r.evaluation.passed ? 'passed' : 'failed'})</div>
            <DimensionBars data={Object.entries(r.evaluation.scores).map(([k, v]) => ({ key: k, value: v }))} labelWidth={140} />
          </div>
          {r.evaluation.findings?.length ? (
            <ul className="list-disc pl-5 text-xs text-gray-700">{r.evaluation.findings.map((f, i) => <li key={i}>{typeof f === 'string' ? f : JSON.stringify(f)}</li>)}</ul>
          ) : null}
        </div>
      )}
      {r.governance?.length > 0 && (
        <div>
          <div className="label">Governance outcomes</div>
          <ul className="space-y-1">
            {r.governance.map((g, i) => (
              <li key={i} className="text-xs flex items-start gap-2">
                <SeverityBadge severity={g.severity} />
                <span><span className="font-mono">{g.rule}</span> · {g.action}: {g.message}{g.required_action && <span className="block text-[#8F2C22]">Required: {g.required_action}</span>}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {Object.keys(rest).length > 0 && <JsonDetails label="Structured output" value={rest} />}
    </div>
  );
}
