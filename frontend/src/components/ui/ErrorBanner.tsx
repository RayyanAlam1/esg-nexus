import { AlertOctagon, AlertTriangle, ShieldOff } from 'lucide-react';
import { isApiError } from '@/api/client';
import { cn } from '@/lib/utils';
import { JsonViewer } from './JsonViewer';

/** Renders API errors; governance_blocked / guardrail_rejected show required action and reason prominently. */
export function ErrorBanner({ error, className, title }: { error: unknown; className?: string; title?: string }) {
  if (!error) return null;
  const api = isApiError(error) ? error : null;
  const code = api?.code ?? 'error';
  const message = api?.message ?? (error instanceof Error ? error.message : String(error));
  const details = api?.details as Record<string, unknown> | unknown[] | null | undefined;
  const isGov = code === 'governance_blocked';
  const isGuard = code === 'guardrail_rejected';
  const detailObj = details && typeof details === 'object' && !Array.isArray(details) ? (details as Record<string, unknown>) : null;
  const required = detailObj?.required_action;
  const reason = detailObj?.reason;
  const Icon = isGov ? ShieldOff : isGuard ? AlertOctagon : AlertTriangle;
  const list = (v: unknown) => (Array.isArray(v) ? v : v ? [v] : []);

  return (
    <div role="alert" className={cn('border rounded-md p-3 text-[13px]', isGov || isGuard ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200', className)}>
      <div className="flex items-start gap-2">
        <Icon size={16} className={cn('mt-0.5 shrink-0', isGov || isGuard ? 'text-[#8F2C22]' : 'text-[#9A5A17]')} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="font-semibold text-gray-900">
            {title ?? (isGov ? 'Blocked by governance rule' : isGuard ? 'Rejected by guardrail' : 'Request failed')}
            <span className="ml-2 text-xxs font-mono text-gray-500">
              {code}
              {api?.status ? ` · ${api.status}` : ''}
            </span>
          </div>
          <div className="text-gray-800">{message}</div>
          {list(reason).length > 0 && (
            <div className="mt-2">
              <div className="text-xxs uppercase tracking-wide text-gray-500 font-semibold">Reason</div>
              <ul className="list-disc pl-5">
                {list(reason).map((r, i) => (
                  <li key={i}>{typeof r === 'string' ? r : JSON.stringify(r)}</li>
                ))}
              </ul>
            </div>
          )}
          {list(required).length > 0 && (
            <div className="mt-2 border-l-2 border-[#8F2C22] pl-2">
              <div className="text-xxs uppercase tracking-wide text-[#8F2C22] font-semibold">Required action</div>
              <ul className="list-disc pl-5 font-medium">
                {list(required).map((r, i) => (
                  <li key={i}>{typeof r === 'string' ? r : JSON.stringify(r)}</li>
                ))}
              </ul>
            </div>
          )}
          {detailObj?.rule ? <div className="mt-1 text-xs text-gray-600">Rule: <span className="font-mono">{String(detailObj.rule)}</span></div> : null}
          {details && !required && !reason ? (
            <details className="mt-2">
              <summary className="text-xs text-gray-600 cursor-pointer">Details</summary>
              <JsonViewer value={details} />
            </details>
          ) : null}
        </div>
      </div>
    </div>
  );
}
