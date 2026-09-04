import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { reseed, useHealth, useReady, useSystem } from '@/api/admin';
import { useAuth } from '@/app/auth';
import { Card, ErrorBanner, JsonViewer, LoadingBlock, Modal, PageHeader, StatCard, StatusBadge } from '@/components/ui';
import { fmtDuration, fmtNumber, titleCase } from '@/lib/format';

export function SystemPage() {
  const { hasCap } = useAuth();
  const qc = useQueryClient();
  const sys = useSystem();
  const health = useHealth();
  const ready = useReady();
  const [confirm, setConfirm] = useState(false);
  const doReseed = useMutation({ mutationFn: reseed, onSuccess: () => { qc.invalidateQueries(); setConfirm(false); } });
  const s = sys.data;
  return (
    <div className="space-y-4">
      <PageHeader
        title="System"
        description="Runtime configuration, database and AI provider, record counts and health probes."
        showScope={false}
        actions={hasCap('tenant.admin') && <button type="button" className="btn-danger" onClick={() => setConfirm(true)}><RefreshCw size={14} /> Reseed reference data</button>}
      />
      {sys.error && <ErrorBanner error={sys.error} />}
      {doReseed.error ? <ErrorBanner error={doReseed.error} /> : null}
      {doReseed.data && <Card title="Reseed result"><JsonViewer value={doReseed.data} /></Card>}
      <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
        <StatCard label="Liveness /health" value={<StatusBadge status={health.data?.status ?? (health.error ? 'error' : 'pending')} />} hint={health.data ? `${health.data.app} · up ${fmtDuration(health.data.uptime_seconds)}` : undefined} />
        <StatCard label="Readiness /health/ready" value={<StatusBadge status={ready.data?.status ?? (ready.error ? 'error' : 'pending')} />} hint={ready.data ? `db ${ready.data.database ?? '—'} · ${ready.data.tenants ?? 0} tenant(s) · ${ready.data.seeded ? 'seeded' : 'not seeded'}` : ready.error ? String(ready.error) : undefined} />
        <StatCard label="Environment" value={<span className="text-base">{s?.environment ?? '—'}</span>} hint={s ? `${s.database} · Python ${s.python}` : undefined} />
        <StatCard label="AI provider" value={<span className="text-base">{s?.ai_provider ?? '—'}</span>} hint={s ? `${s.model} · embeddings ${s.embedding_provider}` : undefined} />
      </div>
      {sys.isLoading ? <LoadingBlock /> : s ? (
        <div className="grid gap-3 lg:grid-cols-2">
          <Card title="Record counts">
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(s.counts).map(([k, v]) => <StatCard key={k} label={titleCase(k)} value={fmtNumber(v)} />)}
            </div>
          </Card>
          <Card title="Tenant & configuration">
            <dl className="kv">
              <dt>Tenant</dt><dd>{s.tenant.name} <span className="text-gray-500">({s.tenant.slug})</span></dd>
              <dt>Deployment</dt><dd>{titleCase(s.tenant.deployment_model)}</dd>
              <dt>Uptime</dt><dd>{fmtDuration(s.uptime_seconds)}</dd>
              {Object.entries(s.config).map(([k, v]) => (<div key={k} className="contents"><dt>{titleCase(k)}</dt><dd className="font-mono text-xs">{String(v)}</dd></div>))}
            </dl>
          </Card>
        </div>
      ) : null}
      <Modal open={confirm} onClose={() => setConfirm(false)} title="Reseed reference data" footer={<><button type="button" className="btn-secondary" onClick={() => setConfirm(false)}>Cancel</button><button type="button" className="btn-danger" onClick={() => doReseed.mutate()} disabled={doReseed.isPending}>{doReseed.isPending ? 'Reseeding…' : 'Reseed now'}</button></>}>
        <p className="text-sm">This reloads the Engro Corporation reference dataset (metrics, values, evidence, frameworks, governance rules) and recomputes derived metrics, quality scores and issues. It is recorded in the audit trail.</p>
      </Modal>
    </div>
  );
}
