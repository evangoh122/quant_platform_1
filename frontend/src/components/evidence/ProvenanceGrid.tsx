import type { ToolCall } from '../../api/types';
import { SourceCard } from './SourceCard';

interface SecRow {
  chunk_id?: string;
  chunk_text?: string;
  accession_number?: string;
  form_type?: string;
  accepted_ts?: string;
  source_url?: string;
  ticker?: string;
  section?: string;
  chunk_index?: number;
  similarity?: number;
  distance?: number;
  rerank_score?: number;
  retrieval_mode?: string;
  error?: string;
  message?: string;
  reason?: string;
}

function isSecRow(row: Record<string, unknown>): row is SecRow & Record<string, unknown> {
  return typeof row === 'object' && row !== null;
}

function safeStr(val: unknown): string | undefined {
  return typeof val === 'string' ? val : undefined;
}

function safeNum(val: unknown): number | undefined {
  return typeof val === 'number' && Number.isFinite(val) ? val : undefined;
}

function hasError(row: SecRow): boolean {
  return typeof row.error === 'string';
}

function errorLabel(row: SecRow): string {
  switch (row.error) {
    case 'no_coverage':
      return `No SEC filings processed for ${safeStr(row.ticker) ?? 'this ticker'} yet`;
    case 'retrieval_unavailable':
      return 'SEC search temporarily unavailable';
    case 'ticker_required':
      return 'Ticker is required for SEC search';
    default:
      return safeStr(row.message) ?? 'Unknown error retrieving SEC data';
  }
}

interface ProvenanceGridProps {
  toolCalls: ToolCall[];
}

export function ProvenanceGrid({ toolCalls }: ProvenanceGridProps) {
  const secCalls = toolCalls.filter((tc) => tc.name === 'search_sec_filings' && tc.ok);

  const goodRows: SecRow[] = [];
  const errorRows: SecRow[] = [];
  for (const tc of secCalls) {
    const rows = tc.result?.rows;
    if (Array.isArray(rows)) {
      for (const row of rows) {
        if (isSecRow(row)) {
          if (hasError(row)) {
            errorRows.push(row);
          } else {
            goodRows.push(row);
          }
        }
      }
    }
  }

  if (goodRows.length === 0 && errorRows.length === 0) return null;

  return (
    <div data-testid="provenance-grid" className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        SEC Sources
      </h3>
      {errorRows.map((row, i) => (
        <div
          key={`err-${safeStr(row.ticker) ?? i}`}
          data-testid="provenance-error"
          className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300"
        >
          {errorLabel(row)}
        </div>
      ))}
      {goodRows.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {goodRows.map((row, i) => (
            <SourceCard
              key={safeStr(row.chunk_id) ?? i}
              ticker={safeStr(row.ticker)}
              formType={safeStr(row.form_type)}
              accessionNumber={safeStr(row.accession_number)}
              acceptedTs={safeStr(row.accepted_ts)}
              section={safeStr(row.section)}
              sourceUrl={safeStr(row.source_url)}
              retrievalMode={safeStr(row.retrieval_mode)}
            />
          ))}
        </div>
      )}
    </div>
  );
}