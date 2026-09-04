import { useAppContext } from '@/app/context';
import type { EntityNode } from '@/api/types';
import { Card, EmptyState, PageHeader, StatusBadge } from '@/components/ui';
import { fmtDate, fmtNumber, titleCase } from '@/lib/format';

function EntityRows({ nodes, depth = 0 }: { nodes: EntityNode[]; depth?: number }) {
  return (
    <>
      {nodes.map((e) => (
        <EntityRow key={e.id} e={e} depth={depth} />
      ))}
    </>
  );
}

function EntityRow({ e, depth }: { e: EntityNode; depth: number }) {
  return (
    <>
      <tr>
        <td><span style={{ paddingLeft: depth * 16 }} className="font-mono text-xs text-navy">{depth > 0 && <span className="text-gray-300 mr-1">└</span>}{e.code}</span></td>
        <td className="font-medium">{e.name}</td>
        <td>{titleCase(e.kind)}</td>
        <td className="text-right tabular-nums">{e.ownership_pct === null ? '—' : `${fmtNumber(e.ownership_pct)}%`}</td>
        <td><StatusBadge status={e.consolidation_method === 'excluded' ? 'rejected' : 'active'} label={titleCase(e.consolidation_method)} /></td>
        <td>{e.in_reporting_boundary ? 'In boundary' : <span className="text-gray-400">Out of boundary</span>}</td>
        <td>{e.country ?? '—'}{e.location ? ` · ${e.location}` : ''}</td>
        <td className="text-xs text-gray-600">{e.sector ?? '—'}</td>
        <td className="text-xs text-gray-600">{Object.entries(e.attributes ?? {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join('/') : String(v)}`).join(' · ') || '—'}</td>
      </tr>
      <EntityRows nodes={e.children ?? []} depth={depth + 1} />
    </>
  );
}

export function OrganizationPage() {
  const { org } = useAppContext();
  if (!org) return <EmptyState title="Organization unavailable" />;
  return (
    <div className="space-y-4">
      <PageHeader title="Organization" description="Legal structure, reporting boundary, entity hierarchy with consolidation methods, and reporting periods." showScope={false} />
      <div className="grid gap-3 lg:grid-cols-2">
        <Card title={`${org.name} (${org.code})`}>
          <dl className="kv">
            <dt>Legal name</dt><dd>{org.legal_name ?? '—'}</dd>
            <dt>Legal form</dt><dd>{org.legal_form ?? '—'}</dd>
            <dt>Headquarters</dt><dd>{org.headquarters ?? '—'}{org.country ? `, ${org.country}` : ''}</dd>
            <dt>Ticker</dt><dd>{org.stock_ticker ?? '—'}</dd>
            <dt>Sector</dt><dd>{org.sector ?? '—'}</dd>
            <dt>Website</dt><dd>{org.website ?? '—'}</dd>
            <dt>Reporting boundary</dt><dd>{org.reporting_boundary ?? '—'}</dd>
            <dt>Description</dt><dd>{org.description ?? '—'}</dd>
          </dl>
        </Card>
        <Card title="Reporting periods" bodyClassName="p-0">
          <table className="table">
            <thead><tr><th>Code</th><th>Label</th><th>Start</th><th>End</th><th>Granularity</th><th>Status</th><th>Baseline</th></tr></thead>
            <tbody>
              {org.periods.map((p) => (
                <tr key={p.id}><td className="font-mono text-xs">{p.code}</td><td>{p.label}</td><td>{fmtDate(p.start_date)}</td><td>{fmtDate(p.end_date)}</td><td>{p.granularity}</td><td><StatusBadge status={p.status} /></td><td>{p.is_baseline ? 'Yes' : ''}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
      <Card title="Entity tree" bodyClassName="p-0" subtitle="Group → subsidiaries / JVs / associates → business units and facilities">
        <div className="overflow-x-auto">
          <table className="table">
            <thead><tr><th>Code</th><th>Name</th><th>Kind</th><th className="text-right">Ownership</th><th>Consolidation</th><th>Boundary</th><th>Location</th><th>Sector</th><th>Attributes</th></tr></thead>
            <tbody><EntityRows nodes={org.entities} /></tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
