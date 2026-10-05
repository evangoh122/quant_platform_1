import type { ToolCall } from '../../api/types';
import { DeveloperDetails } from './DeveloperDetails';

interface ToolCallCardProps {
  toolCall: ToolCall;
  index: number;
}

function deriveBadge(tc: ToolCall): { label: string; cls: string } {
  if (!tc.ok) {
    return { label: 'Failed', cls: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' };
  }
  if (tc.name === 'search_sec_filings') {
    const rows = tc.result?.rows;
    const count = Array.isArray(rows) ? rows.length : undefined;
    return {
      label: count !== undefined ? `${count} source${count !== 1 ? 's' : ''}` : 'SEC search',
      cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
    };
  }
  if (tc.name === 'get_latest_signal') {
    return {
      label: 'Signal',
      cls: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    };
  }
  if (tc.name === 'save_research_note') {
    const noteId = tc.result?.note_id;
    return {
      label: noteId ? `Note ${noteId}` : 'Note saved',
      cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
    };
  }
  if (tc.name === 'add_to_watchlist') {
    return {
      label: 'Watchlist',
      cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
    };
  }
  return {
    label: 'OK',
    cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
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
  if (Array.isArray(rows)) return rows.length;
  return undefined;
}

export function ToolCallCard({ toolCall, index }: ToolCallCardProps) {
  const badge = deriveBadge(toolCall);
  const ticker = deriveTicker(toolCall);
  const sourceCount = deriveSourceCount(toolCall);
  const noteId = typeof toolCall.result?.note_id === 'string' ? toolCall.result.note_id : undefined;
  const isWrite = toolCall.name === 'save_research_note' || toolCall.name === 'add_to_watchlist';

  return (
    <div
      data-testid={`tool-call-${index}`}
      className="rounded-md border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs font-semibold text-slate-800 dark:text-slate-200">
          {toolCall.name}
        </span>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${badge.cls}`}>
          {badge.label}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
        {ticker && (
          <span>
            Ticker: <span className="font-medium text-slate-700 dark:text-slate-300">{ticker}</span>
          </span>
        )}
        {sourceCount !== undefined && (
          <span>
            Sources: <span className="font-medium text-slate-700 dark:text-slate-300">{sourceCount}</span>
          </span>
        )}
        {isWrite && toolCall.ok && noteId && (
          <span>
            Note ID: <span className="font-mono font-medium text-slate-700 dark:text-slate-300">{noteId}</span>
          </span>
        )}
        {isWrite && toolCall.ok && (
          <span>
            Storage: <span className="font-medium text-emerald-600 dark:text-emerald-400">Lakebase</span>
          </span>
        )}
      </div>

      {toolCall.name === 'save_research_note' && toolCall.ok && (
        <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400">
          Research note saved to Lakebase.
        </p>
      )}

      <DeveloperDetails arguments={toolCall.arguments} result={toolCall.result} />
    </div>
  );
}