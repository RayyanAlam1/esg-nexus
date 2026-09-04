import { Check } from 'lucide-react';
import { useRoles } from '@/api/admin';
import { Card, ErrorBanner, LoadingBlock, PageHeader } from '@/components/ui';

export function RolesPage() {
  const q = useRoles();
  const roles = q.data ?? [];
  const caps = Array.from(new Set(roles.flatMap((r) => r.capabilities))).sort();
  return (
    <div className="space-y-4">
      <PageHeader title="Roles & Capabilities" description="Role → capability matrix (RBAC). A capability is granted when any of the user's roles includes it; workflow transitions are additionally restricted by role." showScope={false} />
      {q.error && <ErrorBanner error={q.error} />}
      {q.isLoading ? <LoadingBlock /> : (
        <Card bodyClassName="p-0">
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Capability</th>
                  {roles.map((r) => <th key={r.name} className="text-center whitespace-normal min-w-[88px]">{r.name.replace(/_/g, ' ')}</th>)}
                </tr>
              </thead>
              <tbody>
                {caps.map((c) => (
                  <tr key={c}>
                    <td className="font-mono text-xs">{c}</td>
                    {roles.map((r) => (
                      <td key={r.name} className="text-center">{r.capabilities.includes(c) ? <Check size={14} className="inline text-teal" aria-label={`${r.name} has ${c}`} /> : <span className="text-gray-200">·</span>}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
