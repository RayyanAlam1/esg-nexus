import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { searchKnowledge } from '@/api/agents';
import { Card, EmptyState, ErrorBanner, Input, JsonDetails, PageHeader, ProgressBar, Select } from '@/components/ui';
import { SERIES_PRIMARY } from '@/lib/colors';
import { fmtNumber, titleCase } from '@/lib/format';

const KINDS = ['framework', 'policy', 'report', 'methodology', 'metric_definition', 'evidence', 'internal', 'regulation'];

export function RagPage() {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('');
  const [limit, setLimit] = useState(8);
  const search = useMutation({ mutationFn: () => searchKnowledge(query, limit, kind || undefined) });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (query.trim()) search.mutate();
  };
  const maxScore = Math.max(...(search.data?.hits.map((h) => h.score) ?? [1]), 0.0001);
  return (
    <div className="space-y-4">
      <PageHeader title="RAG Search" description="Retrieve passages from the permission-filtered knowledge base with citations and relevance scores. This is the retrieval layer used by agents and the Copilot." showScope={false} />
      <Card bodyClassName="p-3">
        <form onSubmit={submit} className="grid gap-2 md:grid-cols-[1fr_180px_100px_auto]">
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. Scope 1 emissions methodology, TRIR definition, WEF anti-corruption disclosure" aria-label="Search query" />
          <Select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Document kind">
            <option value="">All kinds</option>
            {KINDS.map((k) => <option key={k} value={k}>{titleCase(k)}</option>)}
          </Select>
          <Select value={limit} onChange={(e) => setLimit(Number(e.target.value))} aria-label="Result limit">
            {[5, 8, 12, 20].map((n) => <option key={n} value={n}>{n} hits</option>)}
          </Select>
          <button type="submit" className="btn-primary" disabled={search.isPending || !query.trim()}><Search size={14} /> Search</button>
        </form>
      </Card>
      {search.error ? <ErrorBanner error={search.error} /> : null}
      {search.data && (
        <Card title={`${search.data.hits.length} hit(s) for “${search.data.query}”`} subtitle={`index ${search.data.index} · permission filtered: ${search.data.permission_filtered ? 'yes' : 'no'}`} bodyClassName="p-0">
          {search.data.hits.length === 0 ? (
            <EmptyState compact title="No passages found" hint="Try different terms; only documents your roles may access are searched." />
          ) : (
            <ul>
              {search.data.hits.map((h, i) => (
                <li key={i} className="px-4 py-3 border-b border-gray-100">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <span className="font-mono text-xs text-navy">{h.citation}</span>
                    <span className="text-xs text-gray-500">{h.title} · {titleCase(h.kind)} · v{h.version}{h.freshness ? ` · ${h.freshness}` : ''}</span>
                    <span className="flex items-center gap-2 text-xs text-gray-600">score {fmtNumber(h.score, { decimals: 3 })}<ProgressBar value={(h.score / maxScore) * 100} color={SERIES_PRIMARY} className="w-24" /></span>
                  </div>
                  <p className="text-[13px] text-gray-800 mt-1 whitespace-pre-line">{h.text}</p>
                  {h.meta && Object.keys(h.meta).length > 0 && <JsonDetails label="Chunk metadata" value={h.meta} />}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </div>
  );
}
