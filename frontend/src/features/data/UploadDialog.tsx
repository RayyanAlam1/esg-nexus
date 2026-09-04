import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { classifyColumns, uploadDataset, useSources } from '@/api/datasets';
import type { AgentResult, UploadResult } from '@/api/types';
import { useAuth } from '@/app/auth';
import { useAppContext } from '@/app/context';
import { ErrorBanner, Field, Input, JsonViewer, Modal, Select, StatCard, StatusBadge } from '@/components/ui';
import { fmtNumber } from '@/lib/format';
import { AgentResultView } from '../ai/AgentResultView';

/** Read the header row (and first rows) of a CSV/JSON file client-side for the classify helper. */
async function readColumns(file: File): Promise<{ columns: string[]; rows: Record<string, unknown>[] }> {
  const text = await file.text();
  if (file.name.toLowerCase().endsWith('.json')) {
    try {
      const data = JSON.parse(text) as unknown;
      const arr = Array.isArray(data) ? data : (data as { rows?: unknown[] }).rows ?? [];
      const rows = (arr as Record<string, unknown>[]).slice(0, 5);
      return { columns: rows.length ? Object.keys(rows[0]) : [], rows };
    } catch {
      return { columns: [], rows: [] };
    }
  }
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  if (!lines.length) return { columns: [], rows: [] };
  const split = (l: string) => l.split(',').map((c) => c.trim().replace(/^"|"$/g, ''));
  const columns = split(lines[0]);
  const rows = lines.slice(1, 6).map((l) => Object.fromEntries(split(l).map((v, i) => [columns[i] ?? `col${i}`, v])));
  return { columns, rows };
}

export function UploadDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { hasCap } = useAuth();
  const { period, entity } = useAppContext();
  const sources = useSources();
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({ dataset_code: '', dataset_name: '', source_code: 'SRC-MANUAL', entity_default: entity, period_default: period, auto_load: true });
  const [result, setResult] = useState<UploadResult | null>(null);
  const [classification, setClassification] = useState<AgentResult | null>(null);

  const upload = useMutation({
    mutationFn: () => uploadDataset({ ...form, file: file as File }),
    onSuccess: (r) => {
      setResult(r);
      qc.invalidateQueries({ queryKey: ['datasets'] });
    },
  });
  const classify = useMutation({
    mutationFn: async () => {
      const { columns, rows } = await readColumns(file as File);
      if (!columns.length) throw new Error('Could not read columns from this file (CSV/JSON header expected).');
      return classifyColumns(columns, rows);
    },
    onSuccess: setClassification,
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (file) upload.mutate();
  };
  const reset = () => {
    setResult(null);
    setClassification(null);
    setFile(null);
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={reset}
      title="Upload dataset"
      width="max-w-3xl"
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={reset}>Close</button>
          {hasCap('ai.run') && (
            <button type="button" className="btn-secondary" onClick={() => classify.mutate()} disabled={!file || classify.isPending}>
              <Sparkles size={14} /> {classify.isPending ? 'Classifying…' : 'Classify columns with ESG Data Agent'}
            </button>
          )}
          <button type="submit" form="upload-form" className="btn-primary" disabled={!file || !form.dataset_code || upload.isPending}>
            {upload.isPending ? 'Uploading…' : 'Upload & validate'}
          </button>
        </>
      }
    >
      <form id="upload-form" onSubmit={submit} className="space-y-3">
        {upload.error ? <ErrorBanner error={upload.error} /> : null}
        {classify.error ? <ErrorBanner error={classify.error} /> : null}
        <Field label="File" required hint="CSV, Excel, JSON, PDF or text. Rows need metric_code, entity_code, period_code and value columns (defaults below fill missing entity/period).">
          <input type="file" className="input" onChange={(e) => setFile(e.target.files?.[0] ?? null)} accept=".csv,.xlsx,.xlsm,.xls,.json,.pdf,.txt,.md" required />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Dataset code" required>
            <Input value={form.dataset_code} onChange={(e) => setForm({ ...form, dataset_code: e.target.value.trim().toUpperCase() })} placeholder="DS-ENV-2023" required />
          </Field>
          <Field label="Dataset name">
            <Input value={form.dataset_name} onChange={(e) => setForm({ ...form, dataset_name: e.target.value })} />
          </Field>
          <Field label="Data source">
            <Select value={form.source_code} onChange={(e) => setForm({ ...form, source_code: e.target.value })}>
              {(sources.data ?? []).map((s) => (
                <option key={s.code} value={s.code}>{s.code} · {s.name}</option>
              ))}
              {!sources.data?.some((s) => s.code === 'SRC-MANUAL') && <option value="SRC-MANUAL">SRC-MANUAL</option>}
            </Select>
          </Field>
          <Field label="Default entity">
            <Input value={form.entity_default} onChange={(e) => setForm({ ...form, entity_default: e.target.value })} />
          </Field>
          <Field label="Default period">
            <Input value={form.period_default} onChange={(e) => setForm({ ...form, period_default: e.target.value })} />
          </Field>
          <label className="flex items-center gap-2 text-sm mt-5">
            <input type="checkbox" checked={form.auto_load} onChange={(e) => setForm({ ...form, auto_load: e.target.checked })} /> Auto-load valid rows into metric values
          </label>
        </div>
      </form>

      {result && (
        <div className="mt-4 border-t border-gray-200 pt-3 space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-navy">Ingestion result</span>
            <StatusBadge status={result.status} />
            {result.dataset_version_id && <span className="text-xs text-gray-500">version #{result.version} (id {result.dataset_version_id})</span>}
          </div>
          {result.guardrail && <ErrorBanner error={new Error(`File rejected by guardrail: ${result.guardrail.findings?.map((f) => f.message).join('; ')}`)} />}
          <div className="grid grid-cols-4 gap-2">
            <StatCard label="Rows" value={fmtNumber(result.rows ?? null)} />
            <StatCard label="Valid rows" value={fmtNumber(result.valid_rows ?? null)} tone={result.valid_rows === result.rows ? 'text-[#1F7A3A]' : 'text-[#9A5A17]'} />
            <StatCard label="Loaded values" value={fmtNumber(result.loaded_values ?? null)} />
            <StatCard label="Quality" value={result.quality && typeof (result.quality as { overall?: number }).overall === 'number' ? fmtNumber((result.quality as { overall: number }).overall, { decimals: 1 }) : '—'} />
          </div>
          <details open>
            <summary className="text-xs text-teal cursor-pointer">Validation result</summary>
            <JsonViewer value={result.validation_result} />
          </details>
          <details>
            <summary className="text-xs text-teal cursor-pointer">Dataset quality</summary>
            <JsonViewer value={result.quality} />
          </details>
        </div>
      )}
      {classification && (
        <div className="mt-4 border-t border-gray-200 pt-3">
          <div className="text-sm font-semibold text-navy mb-2">ESG Data Agent · column classification</div>
          <AgentResultView r={classification} />
        </div>
      )}
    </Modal>
  );
}
