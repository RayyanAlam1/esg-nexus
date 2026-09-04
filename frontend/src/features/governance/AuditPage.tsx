import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAudit } from '@/api/governance';
import type { AuditEntry } from '@/api/types';
import { Card, DataTable, ErrorBanner, Input, JsonDetails, PageHeader, Select, type Column } from '@/components/ui';
import { fmtDateTime } from '@/lib/format';
import { useDebounce } from '@/lib/utils';

const OBJECT_TYPES = ['metric_value', 'metric_definition', 'evidence', 'report', 'report_section', 'issue', 'governance_rule', 'governance_policy', 'user', 'agent_run', 'copilot', 'framework_mapping', 'organization', 'reporting_period', 'target', 'materiality_topic', 'data_source', 'tenant'];

export function AuditPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounce(q, 300);
  const action = params.get('action') ?? '';
  const objectType = params.get('object_type') ?? '';
  const objectId = params.get('object_id') ?? '';
  const dateFrom = params.get('date_from') ?? '';
  const dateTo = params.get('date_to') ?? '';
  const offset = Number(params.get('offset') ?? 0);
  const limit = 50;
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    if (k !== 'offset') p.delete('offset');
    setParams(p, { replace: true });
  };
  const list = useAudit({ q: dq || undefined, action: action || undefined, object_type: objectType || undefined, object_id: objectId || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined, limit, offset });
  const cols: Column<AuditEntry>[] = [
    { key: 'created_at', header: 'When', render: (a) => <span className="whitespace-nowrap">{fmtDateTime(a.created_at)}</span> },
    { key: 'user_email', header: 'User', render: (a) => a.user_email ?? (a.user_id ? `#${a.user_id}` : 'system') },
    { key: 'action', header: 'Action', render: (a) => <span className="font-mono text-xs text-navy">{a.action}</span> },
    { key: 'object_type', header: 'Object type' },
    { key: 'object_id', header: 'Object', render: (a) => <span className="font-mono text-xs">{a.object_id ?? '—'}</span> },
    { key: 'reason', header: 'Reason', render: (a) => <span className="text-xs">{a.reason ?? '—'}</span> },
    { key: 'old_value', header: 'Old value', render: (a) => <JsonDetails label="old" value={a.old_value} /> },
    { key: 'new_value', header: 'New value', render: (a) => <JsonDetails label="new" value={a.new_value} /> },
    { key: 'ip', header: 'IP', render: (a) => <span className="text-xs text-gray-500">{a.ip ?? '—'}</span> },
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Audit Trail" description="Immutable record of every data, evidence, governance, AI and reporting action: who, what, when, why, old and new values." showScope={false} />
      <Card bodyClassName="p-3">
        <div className="grid gap-2 md:grid-cols-6">
          <Input placeholder="Search action, object, reason" value={q} onChange={(e) => { setQ(e.target.value); set('q', e.target.value); }} aria-label="Search audit" />
          <Input placeholder="Action prefix (e.g. report.)" value={action} onChange={(e) => set('action', e.target.value)} aria-label="Action filter" />
          <Select value={objectType} onChange={(e) => set('object_type', e.target.value)} aria-label="Object type"><option value="">All object types</option>{OBJECT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}</Select>
          <Input placeholder="Object id contains" value={objectId} onChange={(e) => set('object_id', e.target.value)} aria-label="Object id filter" />
          <Input type="date" value={dateFrom} onChange={(e) => set('date_from', e.target.value)} aria-label="From date" />
          <Input type="date" value={dateTo} onChange={(e) => set('date_to', e.target.value)} aria-label="To date" />
        </div>
      </Card>
      {list.error && <ErrorBanner error={list.error} />}
      <Card bodyClassName="p-0">
        <DataTable columns={cols} rows={list.data?.items} rowKey={(a) => a.id} loading={list.isLoading} pagination={{ total: list.data?.total ?? 0, limit, offset, onChange: (o) => set('offset', String(o)) }} dense emptyTitle="No audit entries match" />
      </Card>
    </div>
  );
}
