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

function hasError(row: SecRow): boolean {
  return typeof row.error === 'string';
}

interface ProvenanceGridProps {
  toolCalls: ToolCall[];
}

export function ProvenanceGrid({ toolCalls }: ProvenanceGridProps) {
  const secCalls = toolCalls.filter((tc) => tc.name === 'search_sec_filings' && tc.ok);

  const allRows: SecRow[] = [];
  for (const tc of secCalls) {
    const rows = tc.result?.rows;
    if (Array.isArray(rows)) {
      for (const row of rows) {
        if (isSecRow(row) && !hasError(row)) {
          allRows.push(row);
        }
      }
    }
  }

  if (allRows.length === 0) return null;

  return (
    <div data-testid="provenance-grid" className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        SEC Sources
      </h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {allRows.map((row, i) => (
          <SourceCard
            key={row.chunk_id ?? i}
            ticker={row.ticker}
            formType={row.form_type}
            accessionNumber={row.accession_number}
            acceptedTs={row.accepted_ts}
            section={row.section}
            sourceUrl={row.source_url}
            retrievalMode={row.retrieval_mode}
          />
        ))}
      </div>
    </div>
  );
}