import { AlertOctagon, AlertTriangle, Info, MinusCircle, ShieldAlert } from 'lucide-react';
import type { Severity } from '@/api/types';
import { SEVERITY_CLASSES, statusClass } from '@/lib/colors';
import { titleCase } from '@/lib/format';
import { cn } from '@/lib/utils';

export function StatusBadge({ status, className, label }: { status: string | null | undefined; className?: string; label?: string }) {
  if (!status) return <span className="text-gray-400">—</span>;
  return <span className={cn('badge', statusClass(status), className)}>{label ?? titleCase(status)}</span>;
}

const SEV_ICON: Record<Severity, typeof AlertOctagon> = {
  CRITICAL: AlertOctagon,
  HIGH: ShieldAlert,
  MEDIUM: AlertTriangle,
  LOW: Info,
  INFO: MinusCircle,
};

export function SeverityBadge({ severity, className }: { severity: Severity | string | null | undefined; className?: string }) {
  const sev = ((severity ?? 'INFO').toUpperCase() as Severity) in SEV_ICON ? ((severity ?? 'INFO').toUpperCase() as Severity) : 'INFO';
  const Icon = SEV_ICON[sev];
  return (
    <span className={cn('badge', SEVERITY_CLASSES[sev], className)}>
      <Icon size={11} aria-hidden="true" />
      {sev}
    </span>
  );
}

export function Pill({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn('chip', className)}>{children}</span>;
}
