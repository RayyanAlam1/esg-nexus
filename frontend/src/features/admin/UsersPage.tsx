import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { createUser, setUserRoles, useRoles, useUsers, type UserIn } from '@/api/admin';
import type { AdminUser } from '@/api/types';
import { useAppContext } from '@/app/context';
import { Card, DataTable, Drawer, ErrorBanner, Field, Input, PageHeader, Select, StatusBadge, type Column } from '@/components/ui';
import { fmtDateTime } from '@/lib/format';

function RoleChecklist({ roles, value, onChange }: { roles: string[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="grid grid-cols-2 gap-1">
      {roles.map((r) => (
        <label key={r} className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={value.includes(r)} onChange={(e) => onChange(e.target.checked ? [...value, r] : value.filter((x) => x !== r))} /> {r}
        </label>
      ))}
    </div>
  );
}

export function UsersPage() {
  const qc = useQueryClient();
  const users = useUsers();
  const roles = useRoles();
  const { entities } = useAppContext();
  const roleNames = (roles.data ?? []).map((r) => r.name);
  const [create, setCreate] = useState(false);
  const [edit, setEdit] = useState<AdminUser | null>(null);
  const [editRoles, setEditRoles] = useState<string[]>([]);
  const [form, setForm] = useState<UserIn>({ email: '', full_name: '', password: '', roles: ['esg_analyst'], entity_code: '', title: '' });
  const invalidate = () => qc.invalidateQueries({ queryKey: ['admin', 'users'] });
  const doCreate = useMutation({ mutationFn: () => createUser({ ...form, entity_code: form.entity_code || null, title: form.title || null }), onSuccess: () => { invalidate(); setCreate(false); } });
  const doRoles = useMutation({ mutationFn: () => setUserRoles((edit as AdminUser).id, editRoles), onSuccess: () => { invalidate(); setEdit(null); } });

  const cols: Column<AdminUser>[] = [
    { key: 'email', header: 'Email', render: (u) => <span className="font-mono text-xs">{u.email}</span> },
    { key: 'full_name', header: 'Name', render: (u) => <span className="font-medium">{u.full_name}</span> },
    { key: 'title', header: 'Title', render: (u) => u.title ?? '—' },
    { key: 'roles', header: 'Roles', render: (u) => <div className="flex flex-wrap gap-1">{u.roles.map((r) => <span key={r} className="badge bg-navy-50 text-navy border-navy-100">{r}</span>)}</div> },
    { key: 'entity_scope', header: 'Entity scope', render: (u) => (u.entity_scope.length ? u.entity_scope.join(', ') : <span className="text-gray-400">all entities</span>) },
    { key: 'is_active', header: 'Status', render: (u) => <StatusBadge status={u.is_active ? 'active' : 'retired'} label={u.is_active ? 'Active' : 'Inactive'} /> },
    { key: 'created_at', header: 'Created', render: (u) => fmtDateTime(u.created_at) },
    { key: 'actions', header: '', render: (u) => <button type="button" className="btn-secondary btn-sm" onClick={() => { setEdit(u); setEditRoles(u.roles); }}>Edit roles</button> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title="Users" description="Tenant users and their role assignments. Roles map to capabilities (see Roles)." showScope={false} actions={<button type="button" className="btn-primary" onClick={() => setCreate(true)}><Plus size={14} /> New user</button>} />
      {users.error && <ErrorBanner error={users.error} />}
      <Card bodyClassName="p-0"><DataTable columns={cols} rows={users.data} rowKey={(u) => u.id} loading={users.isLoading} dense emptyTitle="No users" /></Card>

      <Drawer open={create} onClose={() => setCreate(false)} title="Create user" footer={<><button type="button" className="btn-secondary" onClick={() => setCreate(false)}>Cancel</button><button type="submit" form="user-form" className="btn-primary" disabled={doCreate.isPending}>Create</button></>}>
        <form id="user-form" onSubmit={(e: FormEvent) => { e.preventDefault(); doCreate.mutate(); }} className="space-y-3">
          {doCreate.error ? <ErrorBanner error={doCreate.error} /> : null}
          <Field label="Email" required><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></Field>
          <Field label="Full name" required><Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required /></Field>
          <Field label="Title"><Input value={form.title ?? ''} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <Field label="Initial password" required hint="The user should change it on first sign-in."><Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={8} /></Field>
          <Field label="Entity scope" hint="Optional: restrict the user to one entity"><Select value={form.entity_code ?? ''} onChange={(e) => setForm({ ...form, entity_code: e.target.value })}><option value="">All entities</option>{entities.map((e) => <option key={e.code} value={e.code}>{e.code} · {e.name}</option>)}</Select></Field>
          <Field label="Roles" required><RoleChecklist roles={roleNames} value={form.roles} onChange={(v) => setForm({ ...form, roles: v })} /></Field>
        </form>
      </Drawer>
      <Drawer open={!!edit} onClose={() => setEdit(null)} title={edit ? `Roles · ${edit.email}` : ''} footer={<><button type="button" className="btn-secondary" onClick={() => setEdit(null)}>Cancel</button><button type="button" className="btn-primary" onClick={() => doRoles.mutate()} disabled={doRoles.isPending || editRoles.length === 0}>Save roles</button></>}>
        {doRoles.error ? <ErrorBanner error={doRoles.error} /> : null}
        <RoleChecklist roles={roleNames} value={editRoles} onChange={setEditRoles} />
        <p className="text-xs text-gray-500 mt-3">Saving replaces all existing assignments (entity scoping is reset to organization level).</p>
      </Drawer>
    </div>
  );
}
