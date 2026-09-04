import { useEffect, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

function useEscape(onClose: () => void, open: boolean) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose, open]);
}

export function Drawer({ open, onClose, title, children, width = 'max-w-xl', footer }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; width?: string; footer?: ReactNode }) {
  useEscape(onClose, open);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-navy/30" onClick={onClose} aria-hidden="true" />
      <aside className={cn('absolute right-0 top-0 h-full w-full bg-white shadow-xl border-l border-gray-200 flex flex-col', width)}>
        <header className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h2 className="text-sm font-semibold text-navy">{title}</h2>
          <button type="button" onClick={onClose} className="btn-ghost btn-sm" aria-label="Close panel">
            <X size={16} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
        {footer && <footer className="border-t border-gray-200 px-4 py-3 flex items-center justify-end gap-2 bg-gray-50">{footer}</footer>}
      </aside>
    </div>
  );
}

export function Modal({ open, onClose, title, children, footer, width = 'max-w-lg' }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; width?: string }) {
  useEscape(onClose, open);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-navy/30" onClick={onClose} aria-hidden="true" />
      <div className={cn('relative bg-white rounded-md shadow-xl border border-gray-200 w-full flex flex-col max-h-[90vh]', width)}>
        <header className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h2 className="text-sm font-semibold text-navy">{title}</h2>
          <button type="button" onClick={onClose} className="btn-ghost btn-sm" aria-label="Close dialog">
            <X size={16} />
          </button>
        </header>
        <div className="p-4 overflow-y-auto">{children}</div>
        {footer && <footer className="border-t border-gray-200 px-4 py-3 flex items-center justify-end gap-2 bg-gray-50">{footer}</footer>}
      </div>
    </div>
  );
}
