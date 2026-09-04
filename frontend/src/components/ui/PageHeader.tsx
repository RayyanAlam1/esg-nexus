import type { ReactNode } from 'react';
import { CalendarDays, Building2 } from 'lucide-react';
import { useAppContext } from '@/app/context';

export function PageHeader({ title, description, actions, showScope = true, children }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; showScope?: boolean; children?: ReactNode }) {
  const { period, entity, entities } = useAppContext();
  const ent = entities.find((e) => e.code === entity);
  return (
    <div className="mb-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-navy leading-6">{title}</h1>
          {description && <p className="text-xs text-gray-600 mt-0.5 max-w-3xl">{description}</p>}
          {showScope && (
            <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-600">
              <span className="inline-flex items-center gap-1">
                <CalendarDays size={12} aria-hidden="true" /> {period || '—'}
              </span>
              <span className="inline-flex items-center gap-1">
                <Building2 size={12} aria-hidden="true" /> {ent ? `${ent.code} · ${ent.name}` : entity || '—'}
              </span>
            </div>
          )}
        </div>
        {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
      </div>
      {children}
    </div>
  );
}
