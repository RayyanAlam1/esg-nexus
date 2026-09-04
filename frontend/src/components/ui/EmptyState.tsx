import { Database } from 'lucide-react';
import type { ReactNode } from 'react';
import { UNAVAILABLE } from '@/lib/format';
import { cn } from '@/lib/utils';

export function EmptyState({ title = UNAVAILABLE, hint, action, className, compact }: { title?: string; hint?: string; action?: ReactNode; className?: string; compact?: boolean }) {
  return (
    <div className={cn('flex flex-col items-center justify-center text-center text-gray-500', compact ? 'py-4' : 'py-10', className)}>
      <Database size={compact ? 16 : 22} className="text-gray-300 mb-2" aria-hidden="true" />
      <div className="text-sm font-medium text-gray-600">{title}</div>
      {hint && <div className="text-xs mt-1 max-w-md">{hint}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton', className ?? 'h-4 w-full')} />;
}

export function LoadingBlock({ lines = 4 }: { lines?: number }) {
  return (
    <div className="space-y-2 p-4" aria-busy="true" aria-live="polite">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cn('h-3.5', i % 3 === 0 ? 'w-2/3' : i % 3 === 1 ? 'w-full' : 'w-1/2')} />
      ))}
    </div>
  );
}
