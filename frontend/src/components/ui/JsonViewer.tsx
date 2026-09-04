import { cn } from '@/lib/utils';

export function JsonViewer({ value, className, maxHeight = 320 }: { value: unknown; className?: string; maxHeight?: number }) {
  if (value === null || value === undefined) return <span className="text-gray-400">—</span>;
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return (
    <pre className={cn('mono bg-gray-50 border border-gray-200 rounded p-2 overflow-auto whitespace-pre-wrap break-words', className)} style={{ maxHeight }}>
      {text}
    </pre>
  );
}

export function JsonDetails({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) return <span className="text-gray-400">—</span>;
  return (
    <details>
      <summary className="text-xs text-teal cursor-pointer">{label}</summary>
      <JsonViewer value={value} className="mt-1" />
    </details>
  );
}
