import type { ToolCall } from '../../api/types';
import { DeveloperDetails } from './DeveloperDetails';

interface ToolCallCardProps {
  toolCall: ToolCall;
  index: number;
}

export function hasValidNoteId(tc: ToolCall): boolean {
  return typeof tc.result?.note_id === 'string' && tc.result.note_id.trim().length > 0;
}

function deriveBadge(tc: ToolCall): { label: string; cls: string } {
  if (!tc.ok) {
    return { label: 'Failed', cls: 'bg-[var(--danger-fill)] text-[var(--on-danger)]' };
  }
  if (tc.name === 'search_sec_filings') {
    const rows = tc.result?.rows;
    if (!Array.isArray(rows)) {
      return {
        label: 'SEC search',
        cls: 'bg-[var(--success-fill)] text-[var(--on-success)]',
      };
    }
    const nonError = rows.filter(
      (r) => typeof r === 'object' && r !== null && typeof (r as Record<string, unknown>).error !== 'string',
    );
    return {
      label: `${nonError.length} source${nonError.length !== 1 ? 's' : ''}`,
      cls: 'bg-[var(--success-fill)] text-[var(--on-success)]',
    };
  }
  if (tc.name === 'get_latest_signal') {
    return {
      label: 'Signal',
      cls: 'bg-[var(--accent-dim)] text-[var(--accent-bright)]',
    };
  }
  if (tc.name === 'save_research_note') {
    if (hasValidNoteId(tc)) {
      return {
        label: `Note ${tc.result!.note_id}`,
        cls: 'bg-[var(--success-fill)] text-[var(--on-success)]',
      };
    }
    return {
      label: 'Save not confirmed',
      cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
    };
  }
  if (tc.name === 'add_to_watchlist') {
    return {
      label: 'Watchlist',
      cls: 'bg-[var(--success-fill)] text-[var(--on-success)]',
    };
  }
  return {
    label: 'OK',
    cls: 'bg-[var(--success-fill)] text-[var(--on-success)]',
  };
}

function deriveTicker(tc: ToolCall): string | undefined {
  if (tc.arguments?.ticker) return String(tc.arguments.ticker);
  if (tc.arguments?.symbol) return String(tc.arguments.symbol);
  if (tc.result?.symbol) return String(tc.result.symbol);
  const rows = tc.result?.rows;
  if (Array.isArray(rows) && rows.length > 0 && rows[0]?.ticker) {
    return String(rows[0].ticker);
  }
  return undefined;
}

function deriveSourceCount(tc: ToolCall): number | undefined {
  const rows = tc.result?.rows;
  if (!Array.isArray(rows)) return undefined;
  const nonError = rows.filter(
    (r) => typeof r === 'object' && r !== null && typeof (r as Record<string, unknown>).error !== 'string',
  );
  return nonError.length;
}

export function ToolCallCard({ toolCall, index }: ToolCallCardProps) {
  const badge = deriveBadge(toolCall);
  const ticker = deriveTicker(toolCall);
  const sourceCount = deriveSourceCount(toolCall);
  const noteId = hasValidNoteId(toolCall) ? String(toolCall.result!.note_id) : undefined;
  const isWrite = toolCall.name === 'save_research_note' || toolCall.name === 'add_to_watchlist';

  return (
    <div
      data-testid={`tool-call-${index}`}
      className="rounded-md border border-[var(--border)] bg-[var(--surface)] p-3"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs font-semibold text-[var(--text-primary)]">
          {toolCall.name}
        </span>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}>
          {badge.label}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--text-muted)]">
        {ticker && (
          <span>
            Ticker: <span className="font-medium text-[var(--text-secondary)]">{ticker}</span>
          </span>
        )}
        {sourceCount !== undefined && (
          <span>
            Sources: <span className="font-medium text-[var(--text-secondary)]">{sourceCount}</span>
          </span>
        )}
        {isWrite && toolCall.ok && noteId && (
          <span>
            Note ID: <span className="font-mono font-medium text-[var(--text-secondary)]">{noteId}</span>
          </span>
        )}
        {toolCall.name === 'add_to_watchlist' && toolCall.ok && (
          <span>
            Storage: <span className="font-medium text-[var(--on-success)]">Lakebase</span>
          </span>
        )}
        {toolCall.name === 'save_research_note' && toolCall.ok && noteId && (
          <span>
            Storage: <span className="font-medium text-[var(--on-success)]">Lakebase</span>
          </span>
        )}
      </div>

      {toolCall.name === 'save_research_note' && toolCall.ok && noteId && (
        <p className="mt-2 text-xs text-[var(--on-success)]">
          Research note saved to Lakebase.
        </p>
      )}

      <DeveloperDetails arguments={toolCall.arguments} result={toolCall.result} />
    </div>
  );
}
