import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface TabDef {
  key: string;
  label: ReactNode;
  count?: number;
}

export function Tabs({ tabs, active, onChange, className }: { tabs: TabDef[]; active: string; onChange: (k: string) => void; className?: string }) {
  return (
    <div role="tablist" className={cn('flex items-center gap-1 border-b border-gray-200 overflow-x-auto', className)}>
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          aria-selected={active === t.key}
          type="button"
          onClick={() => onChange(t.key)}
          className={cn(
            'px-3 py-2 text-[13px] border-b-2 -mb-px whitespace-nowrap transition-colors',
            active === t.key ? 'border-teal text-navy font-semibold' : 'border-transparent text-gray-600 hover:text-navy',
          )}
        >
          {t.label}
          {t.count !== undefined && <span className="ml-1.5 text-xxs bg-gray-100 text-gray-600 rounded px-1 py-0.5 tabular-nums">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}
