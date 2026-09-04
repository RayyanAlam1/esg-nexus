import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Send, ShieldCheck, ShieldOff, UserCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { askCopilot, useSuggestions } from '@/api/agents';
import type { CopilotAnswer, GovernanceOutcome } from '@/api/types';
import { useAppContext } from '@/app/context';
import { ErrorBanner, MarkdownView, SeverityBadge, StatusBadge, ConfidenceBar, JsonDetails, Pill } from '@/components/ui';
import { cn } from '@/lib/utils';

interface Message {
  role: 'user' | 'assistant';
  text: string;
  answer?: CopilotAnswer;
  error?: unknown;
}

function GovernanceList({ items }: { items: GovernanceOutcome[] | undefined }) {
  if (!items?.length) return null;
  return (
    <ul className="space-y-1 mt-2">
      {items.map((g, i) => (
        <li key={i} className="flex items-start gap-2 text-xs">
          <SeverityBadge severity={g.severity} />
          <span>
            <span className="font-mono">{g.rule}</span> · {g.action}: {g.message ?? '—'}
            {g.required_action && <span className="block text-[#8F2C22]">Required: {g.required_action}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function CopilotAnswerView({ a, compact }: { a: CopilotAnswer; compact?: boolean }) {
  const experts = (a.experts ?? []).map((e) => (typeof e === 'string' ? e : e.name));
  const evidence = a.evidence ?? [];
  const guard = a.guardrail;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <StatusBadge status={a.status} />
        {a.requires_human_review && (
          <span className="badge bg-amber-50 text-[#7A6215] border-amber-200">
            <UserCheck size={11} /> Human review required
          </span>
        )}
        <ConfidenceBar value={a.confidence} />
      </div>
      <MarkdownView content={a.answer} />
      {a.sources?.length > 0 && (
        <div>
          <div className="label">Sources</div>
          <div className="flex flex-wrap gap-1">
            {a.sources.map((s, i) => (
              <Pill key={i} className="font-mono text-xxs">
                {s}
              </Pill>
            ))}
          </div>
        </div>
      )}
      {a.metrics_used?.length > 0 && (
        <div>
          <div className="label">Metrics used</div>
          <div className="flex flex-wrap gap-1">
            {a.metrics_used.map((m) => (
              <Link key={m} to={`/metrics/${encodeURIComponent(m)}`} className="chip hover:border-teal font-mono text-xxs">
                {m}
              </Link>
            ))}
          </div>
        </div>
      )}
      {evidence.length > 0 && (
        <div>
          <div className="label">Evidence</div>
          <div className="flex flex-wrap gap-1">
            {evidence.map((e) => (
              <Link key={e} to={`/evidence/${encodeURIComponent(e)}`} className="chip hover:border-teal font-mono text-xxs">
                {e}
              </Link>
            ))}
          </div>
        </div>
      )}
      {experts.length > 0 && (
        <div className="text-xs text-gray-600">
          Experts routed: <span className="font-medium text-gray-800">{experts.join(', ')}</span>
          {a.route?.method && <span className="text-gray-400"> · {a.route.method}</span>}
        </div>
      )}
      <GovernanceList items={a.governance} />
      {guard && (
        <div className="text-xs text-gray-600 flex items-start gap-1.5">
          {guard.blocked ? <ShieldOff size={13} className="text-[#8F2C22] mt-0.5" /> : <ShieldCheck size={13} className="text-[#1F7A3A] mt-0.5" />}
          <span>
            Guardrail {guard.blocked ? 'blocked' : guard.passed ? 'passed' : 'flagged'}
            {guard.injection_detected && ' · injection detected'}
            {guard.unsupported_numbers?.length ? ` · unsupported numbers: ${guard.unsupported_numbers.join(', ')}` : ''}
            {guard.findings?.length ? ` · ${guard.findings.length} finding(s)` : ''}
          </span>
        </div>
      )}
      {!compact && a.evaluation && (
        <div className="text-xs text-gray-600">
          Evaluation: <span className="font-medium">{a.evaluation.overall}</span> ({a.evaluation.passed ? 'passed' : 'failed'}) ·{' '}
          {Object.entries(a.evaluation.scores ?? {})
            .map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`)
            .join(' · ')}
        </div>
      )}
      {!compact && a.extras && Object.keys(a.extras).length > 0 && <JsonDetails label="Additional output (gaps, recommendations, findings)" value={a.extras} />}
      {a.disclaimer && <p className="text-xxs text-gray-500 border-t border-gray-100 pt-1">{a.disclaimer}</p>}
    </div>
  );
}

export function CopilotChat({ compact, initialQuestion }: { compact?: boolean; initialQuestion?: string }) {
  const { period, entity } = useAppContext();
  const suggestions = useSuggestions();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState(initialQuestion ?? '');
  const bottomRef = useRef<HTMLDivElement>(null);

  const ask = useMutation({
    mutationFn: (q: string) => askCopilot({ question: q, period_code: period || null, entity_code: entity || null }),
    onSuccess: (answer) => setMessages((m) => [...m, { role: 'assistant', text: answer.answer, answer }]),
    onError: (error) => setMessages((m) => [...m, { role: 'assistant', text: '', error }]),
  });

  const send = (q: string) => {
    const text = q.trim();
    if (!text || ask.isPending) return;
    setMessages((m) => [...m, { role: 'user', text }]);
    setInput('');
    ask.mutate(text);
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, ask.isPending]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {messages.length === 0 && (
          <div className="text-xs text-gray-600">
            <p className="mb-2">
              Ask about metrics, disclosures, evidence and readiness for <span className="font-medium">{period || 'the current period'}</span> / <span className="font-medium">{entity || 'group'}</span>. Answers are grounded in governed data with citations.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {(suggestions.data ?? []).map((s) => (
                <button key={s} type="button" className="chip hover:border-teal text-left" onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={cn('rounded-md border p-3', m.role === 'user' ? 'bg-navy-50 border-navy-100 ml-8' : 'bg-white border-gray-200 mr-2')}>
            {m.role === 'user' ? (
              <p className="text-[13px] text-navy">{m.text}</p>
            ) : m.error ? (
              <ErrorBanner error={m.error} />
            ) : m.answer ? (
              <CopilotAnswerView a={m.answer} compact={compact} />
            ) : null}
          </div>
        ))}
        {ask.isPending && <div className="text-xs text-gray-500 animate-pulse">Routing to experts, retrieving governed facts…</div>}
        <div ref={bottomRef} />
      </div>
      <form
        className="mt-2 flex items-end gap-2 border-t border-gray-200 pt-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <textarea
          className="input flex-1 min-h-[40px] max-h-32 resize-y"
          placeholder="Ask the ESG Copilot…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          aria-label="Copilot question"
        />
        <button type="submit" className="btn-accent" disabled={ask.isPending || !input.trim()} aria-label="Send question">
          <Send size={14} />
        </button>
      </form>
      <p className="text-xxs text-gray-400 mt-1">Advisory only — not a compliance opinion. Outputs pass guardrails, evaluation and governance before use.</p>
    </div>
  );
}
