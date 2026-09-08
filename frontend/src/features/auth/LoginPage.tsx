import { useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/app/auth';
import { ErrorBanner, Field, Input } from '@/components/ui';

// Shown only in development builds: these are seeded reference-data accounts and must never
// appear in a deployed environment.
const SHOW_DEMO_ACCOUNTS = import.meta.env.DEV;

const DEMO_ACCOUNTS: { email: string; password: string; role: string }[] = [
  { email: 'admin@esgnexus.local', password: 'Admin!2024', role: 'super_admin + org_admin' },
  { email: 'cso@ecorp.local', password: 'Exec!2024', role: 'executive' },
  { email: 'manager@ecorp.local', password: 'Manager!2024', role: 'esg_manager' },
  { email: 'analyst@ecorp.local', password: 'Analyst!2024', role: 'esg_analyst' },
  { email: 'contributor@ecorp.local', password: 'Data!2024', role: 'data_contributor' },
  { email: 'reviewer@ecorp.local', password: 'Review!2024', role: 'reviewer' },
  { email: 'approver@ecorp.local', password: 'Approve!2024', role: 'report_approver' },
  { email: 'auditor@ecorp.local', password: 'Audit!2024', role: 'auditor' },
];

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e?: FormEvent, creds?: { email: string; password: string }) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(creds?.email ?? email, creds?.password ?? password);
      navigate(params.get('next') ?? '/', { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-full flex items-center justify-center bg-gray-50 p-6">
      <div className="w-full max-w-4xl grid md:grid-cols-[1fr_1.1fr] card overflow-hidden">
        <div className="bg-navy text-white p-8 flex flex-col">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center justify-center w-8 h-8 rounded bg-teal font-bold">N</span>
            <span className="text-lg font-semibold">ESG Nexus</span>
          </div>
          <p className="mt-6 text-sm text-white/80 leading-6">Enterprise ESG Intelligence, Governance &amp; Reporting. Every number is traceable to evidence; AI outputs pass guardrails, evaluation and governance before use.</p>
          <form onSubmit={submit} className="mt-8 space-y-3">
            <Field label={<span className="text-white/80">Email</span>} required>
              <Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required className="text-gray-900" />
            </Field>
            <Field label={<span className="text-white/80">Password</span>} required>
              <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required className="text-gray-900" />
            </Field>
            {error ? <ErrorBanner error={error} /> : null}
            <button type="submit" className="btn-accent w-full justify-center" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>
        {SHOW_DEMO_ACCOUNTS ? (
        <div className="p-6">
          <h2 className="text-sm font-semibold text-navy">Demo accounts</h2>
          <p className="text-xs text-gray-600 mb-3">Seeded tenant: Engro Corporation (ECORP), FY2022–FY2023. Click a row to sign in with that persona.</p>
          <table className="table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Password</th>
                <th>Roles</th>
              </tr>
            </thead>
            <tbody>
              {DEMO_ACCOUNTS.map((a) => (
                <tr key={a.email} className="cursor-pointer" onClick={() => submit(undefined, a)}>
                  <td className="font-mono text-xs">{a.email}</td>
                  <td className="font-mono text-xs">{a.password}</td>
                  <td className="text-xs">{a.role}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xxs text-gray-400 mt-3">Backend expected at /api/v1 (proxied to http://localhost:8000 in development).</p>
        </div>
        ) : (
          <div className="p-6 flex items-center">
            <p className="text-sm text-gray-600">
              Sign in with the account provided by your organisation&apos;s ESG Nexus administrator. Contact them if you need access or a password reset.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
