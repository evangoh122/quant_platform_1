import { useState } from 'react';
import { api } from '../api/client';
import type { ChatResponse } from '../api/types';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';

const LINK_KEYS = ['edgar_url', 'url', 'source_url', 'href'];

function rowLink(row: Record<string, unknown>): string | null {
  for (const key of LINK_KEYS) {
    const value = row[key];
    if (typeof value === 'string' && value.length > 0) return value;
  }
  return null;
}

export function SecFilingExplorer() {
  const [input, setInput] = useState('');
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    const symbol = input.trim().toUpperCase();
    if (!symbol) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.chat(`search SEC filings for ${symbol}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const tool = result?.tool_calls[0];
  const rows: Record<string, unknown>[] = (tool?.result && typeof tool.result === 'object' && Array.isArray(tool.result.rows))
    ? (tool.result.rows as Record<string, unknown>[])
    : [];

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">SEC Filing Explorer</h1>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          placeholder="Search filings for a symbol (e.g. NVDA)"
        />
        <button
          type="submit"
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-slate-100 dark:text-slate-900"
        >
          Search
        </button>
      </form>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={() => void run()} />}

      {!loading && !error && (
        <Card title="Extracted Sections & Sources" subtitle="silver_sec_sections">
          {rows.length === 0 ? (
            <EmptyState
              title="No SEC filing sections yet"
              detail="silver_sec_sections is empty — filing sections and extracted events appear once the SEC ingestion and chunking pipeline has run."
            />
          ) : (
            <ul className="space-y-2">
              {rows.map((row, i) => {
                const link = rowLink(row);
                const text = typeof row.chunk_text === 'string' ? row.chunk_text : '';
                const section = typeof row.section === 'string' ? row.section : typeof row.filing_section === 'string' ? row.filing_section : '';
                return (
                  <li key={i} className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
                    {section && <div className="text-xs font-semibold text-slate-500">{section}</div>}
                    <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">{text.slice(0, 320)}</p>
                    {link && (
                      <a href={link} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs text-blue-600 underline dark:text-blue-400">
                        View source
                      </a>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      )}
    </div>
  );
}
