import type { ReactNode } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { EmptyState } from './EmptyState';

export interface Column<T> {
  key: string;
  header: ReactNode;
  render?: (row: T) => ReactNode;
  sortable?: boolean;
  className?: string;
  width?: string;
  align?: 'left' | 'right' | 'center';
}

export interface Pagination {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}

export interface SortState {
  sort?: string;
  order?: 'asc' | 'desc';
  onChange: (sort: string, order: 'asc' | 'desc') => void;
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string | number;
  loading?: boolean;
  pagination?: Pagination;
  sort?: SortState;
  onRowClick?: (row: T) => void;
  emptyTitle?: string;
  emptyHint?: string;
  dense?: boolean;
  rowClassName?: (row: T) => string | undefined;
  footer?: ReactNode;
}

export function DataTable<T>({ columns, rows, rowKey, loading, pagination, sort, onRowClick, emptyTitle, emptyHint, dense, rowClassName, footer }: Props<T>) {
  const toggleSort = (key: string) => {
    if (!sort) return;
    const nextOrder = sort.sort === key && sort.order === 'asc' ? 'desc' : 'asc';
    sort.onChange(key, nextOrder);
  };
  return (
    <div className="w-full">
      <div className="overflow-x-auto">
        <table className="table">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} style={{ width: c.width }} className={cn(c.align === 'right' && 'text-right', c.align === 'center' && 'text-center')}>
                  {c.sortable && sort ? (
                    <button type="button" onClick={() => toggleSort(c.key)} className="inline-flex items-center gap-1 hover:text-navy">
                      {c.header}
                      {sort.sort === c.key ? sort.order === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} /> : <ArrowUpDown size={11} className="text-gray-300" />}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && !rows?.length
              ? Array.from({ length: 6 }).map((_, i) => (
                  <tr key={`sk-${i}`}>
                    {columns.map((c) => (
                      <td key={c.key}>
                        <div className="skeleton h-3.5 w-3/4" />
                      </td>
                    ))}
                  </tr>
                ))
              : rows?.map((row) => (
                  <tr
                    key={rowKey(row)}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={cn(onRowClick && 'cursor-pointer', dense && '[&>td]:py-1', rowClassName?.(row))}
                  >
                    {columns.map((c) => (
                      <td key={c.key} className={cn(c.className, c.align === 'right' && 'text-right tabular-nums', c.align === 'center' && 'text-center')}>
                        {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? '—')}
                      </td>
                    ))}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
      {!loading && rows && rows.length === 0 && <EmptyState title={emptyTitle ?? 'No records'} hint={emptyHint} />}
      {(pagination || footer) && (
        <div className="flex items-center justify-between px-3 py-2 border-t border-gray-200 text-xs text-gray-600">
          <div>{footer}</div>
          {pagination && pagination.total > 0 && (
            <div className="flex items-center gap-2">
              <span className="tabular-nums">
                {pagination.offset + 1}–{Math.min(pagination.offset + pagination.limit, pagination.total)} of {pagination.total.toLocaleString()}
              </span>
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={pagination.offset === 0}
                onClick={() => pagination.onChange(Math.max(0, pagination.offset - pagination.limit))}
                aria-label="Previous page"
              >
                <ChevronLeft size={14} />
              </button>
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={pagination.offset + pagination.limit >= pagination.total}
                onClick={() => pagination.onChange(pagination.offset + pagination.limit)}
                aria-label="Next page"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
