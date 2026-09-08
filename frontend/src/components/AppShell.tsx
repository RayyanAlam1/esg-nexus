import { useState } from 'react';
import { Bell, ChevronRight, LogOut, Menu, MessageSquare, User as UserIcon } from 'lucide-react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { useNotifications } from '@/api/admin';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { NAV, SEGMENT_TITLES } from '@/app/nav';
import { CopilotChat } from '@/features/ai/CopilotChat';
import { fmtDateTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import { Drawer } from './ui/Overlay';

function Sidebar({ collapsed }: { collapsed: boolean }) {
  const { hasCap } = useAuth();
  return (
    <nav aria-label="Primary" className={cn('bg-navy text-white flex flex-col shrink-0 h-full overflow-y-auto transition-[width]', collapsed ? 'w-14' : 'w-56')}>
      <div className="flex items-center gap-2 px-3 h-12 border-b border-white/10">
        <span className="inline-flex items-center justify-center w-7 h-7 rounded bg-teal text-white font-bold text-sm">N</span>
        {!collapsed && (
          <div className="leading-tight">
            <div className="text-sm font-semibold">ESG Nexus</div>
            <div className="text-[10px] text-white/60 uppercase tracking-wider">Intelligence · Governance</div>
          </div>
        )}
      </div>
      <div className="py-2">
        {NAV.filter((g) => !g.cap || hasCap(g.cap)).map((g) => (
          <div key={g.label} className="mb-1">
            {!collapsed && <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-white/50 font-semibold">{g.label}</div>}
            {g.items
              .filter((i) => !i.cap || hasCap(i.cap))
              .map((i) => (
                <NavLink
                  key={i.to}
                  to={i.to}
                  end={i.end}
                  title={i.label}
                  className={({ isActive }) =>
                    cn('flex items-center gap-2.5 px-3 py-1.5 text-[13px] text-white/80 hover:bg-white/10 hover:text-white border-l-2 border-transparent', isActive && 'bg-white/10 text-white border-teal')
                  }
                >
                  <i.icon size={15} aria-hidden="true" className="shrink-0" />
                  {!collapsed && <span className="truncate">{i.label}</span>}
                </NavLink>
              ))}
          </div>
        ))}
      </div>
    </nav>
  );
}

function Breadcrumbs() {
  const { pathname } = useLocation();
  const segs = pathname.split('/').filter(Boolean);
  const crumbs = segs.map((s, i) => ({ label: SEGMENT_TITLES[s] ?? decodeURIComponent(s), to: `/${segs.slice(0, i + 1).join('/')}` }));
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-xs text-gray-500 min-w-0">
      <Link to="/" className="hover:text-navy">
        Home
      </Link>
      {crumbs.map((c, i) => (
        <span key={c.to} className="flex items-center gap-1 min-w-0">
          <ChevronRight size={12} aria-hidden="true" />
          {i === crumbs.length - 1 ? <span className="text-gray-800 font-medium truncate">{c.label}</span> : <Link to={c.to} className="hover:text-navy truncate">{c.label}</Link>}
        </span>
      ))}
    </nav>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const q = useNotifications();
  const unread = (q.data ?? []).filter((n) => !n.is_read).length;
  return (
    <div className="relative">
      <button type="button" className="btn-ghost btn-sm relative" aria-label={`Notifications (${unread} unread)`} onClick={() => setOpen((o) => !o)}>
        <Bell size={16} />
        {unread > 0 && <span className="absolute -top-0.5 -right-0.5 bg-[#B03A2E] text-white text-[9px] rounded-full min-w-[14px] h-[14px] px-0.5 flex items-center justify-center">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-80 card shadow-lg z-30 max-h-96 overflow-y-auto" role="dialog" aria-label="Notifications">
          <div className="card-header">
            <span className="card-title">Notifications</span>
            <button type="button" className="text-xs text-gray-500" onClick={() => setOpen(false)}>
              Close
            </button>
          </div>
          {(q.data ?? []).length === 0 ? (
            <div className="p-3 text-xs text-gray-500">No notifications.</div>
          ) : (
            <ul>
              {(q.data ?? []).map((n) => (
                <li key={n.id} className={cn('px-3 py-2 border-b border-gray-100 text-xs', !n.is_read && 'bg-navy-50/50')}>
                  <div className="font-medium text-gray-800">{n.title}</div>
                  {n.body && <div className="text-gray-600">{n.body}</div>}
                  <div className="text-gray-400 mt-0.5">{fmtDateTime(n.created_at)}</div>
                  {n.link && (
                    <Link to={n.link} className="text-teal" onClick={() => setOpen(false)}>
                      Open
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function Topbar({ onToggleSidebar, onOpenCopilot }: { onToggleSidebar: () => void; onOpenCopilot: () => void }) {
  const { user, logout, hasCap } = useAuth();
  const { org, periods, entities, period, entity, setPeriod, setEntity } = useAppContext();
  const [menu, setMenu] = useState(false);
  return (
    <header className="h-12 bg-white border-b border-gray-200 flex items-center gap-3 px-3 shrink-0">
      <button type="button" className="btn-ghost btn-sm" onClick={onToggleSidebar} aria-label="Toggle navigation">
        <Menu size={16} />
      </button>
      <div className="font-semibold text-navy text-sm truncate max-w-[220px]" title={org?.name}>
        {org?.name ?? '—'}
        {org?.code && <span className="text-gray-400 font-normal ml-1">({org.code})</span>}
      </div>
      <div className="hidden md:block flex-1 min-w-0">
        <Breadcrumbs />
      </div>
      <label className="flex items-center gap-1 text-xs text-gray-600">
        <span className="hidden lg:inline">Period</span>
        <select className="input py-1 w-28" value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Reporting period">
          {periods.map((p) => (
            <option key={p.code} value={p.code}>
              {p.code}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-1 text-xs text-gray-600">
        <span className="hidden lg:inline">Entity</span>
        <select className="input py-1 w-44" value={entity} onChange={(e) => setEntity(e.target.value)} aria-label="Reporting entity">
          {entities.map((e) => (
            <option key={e.code} value={e.code}>
              {`${' '.repeat(e.depth * 2)}${e.code} · ${e.name}`}
            </option>
          ))}
        </select>
      </label>
      <Notifications />
      {hasCap('ai.run') && (
        <button type="button" className="btn-accent btn-sm" onClick={onOpenCopilot}>
          <MessageSquare size={14} /> Copilot
        </button>
      )}
      <div className="relative">
        <button type="button" className="btn-ghost btn-sm" onClick={() => setMenu((m) => !m)} aria-label="User menu" aria-expanded={menu}>
          <UserIcon size={16} />
          <span className="hidden xl:inline text-xs">{user?.full_name}</span>
        </button>
        {menu && (
          <div className="absolute right-0 mt-1 w-64 card shadow-lg z-30 p-3 text-xs" role="menu">
            <div className="font-medium text-gray-900">{user?.full_name}</div>
            <div className="text-gray-500">{user?.email}</div>
            {user?.title && <div className="text-gray-500">{user.title}</div>}
            <div className="mt-2 flex flex-wrap gap-1">
              {user?.roles.map((r) => (
                <span key={r} className="badge bg-navy-50 text-navy border-navy-100">
                  {r}
                </span>
              ))}
            </div>
            <details className="mt-2">
              <summary className="cursor-pointer text-gray-600">Capabilities ({user?.capabilities.length ?? 0})</summary>
              <div className="mt-1 text-gray-600 font-mono text-xxs break-words">{user?.capabilities.join(', ')}</div>
            </details>
            <button type="button" className="btn-secondary btn-sm mt-3 w-full justify-center" onClick={logout}>
              <LogOut size={13} /> Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const [copilot, setCopilot] = useState(false);
  const { orgLoading } = useAppContext();
  const { pathname } = useLocation();
  return (
    <div className="flex h-full">
      <Sidebar collapsed={collapsed} />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar onToggleSidebar={() => setCollapsed((c) => !c)} onOpenCopilot={() => setCopilot(true)} />
        <main className="flex-1 overflow-y-auto p-4">
          {orgLoading ? (
            <div className="text-sm text-gray-500 p-6" aria-busy="true">
              Loading organization context…
            </div>
          ) : (
            <ErrorBoundary resetKey={pathname} label="This page">
              <Outlet />
            </ErrorBoundary>
          )}
        </main>
      </div>
      <Drawer open={copilot} onClose={() => setCopilot(false)} title="ESG Copilot" width="max-w-2xl">
        <div className="h-full">
          <CopilotChat compact />
        </div>
      </Drawer>
    </div>
  );
}
