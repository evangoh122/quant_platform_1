import type { ToolCall } from '../../api/types';
import { ToolCallCard } from './ToolCallCard';
import { ProvenanceGrid } from './ProvenanceGrid';

interface EvidencePanelProps {
  toolCalls: ToolCall[];
  available: boolean;
  sending: boolean;
}

export function EvidencePanel({ toolCalls, available, sending }: EvidencePanelProps) {
  if (toolCalls.length === 0 && !sending) {
    return (
      <div
        data-testid="evidence-panel-empty"
        data-tour="agent-evidence"
        className="flex flex-col items-center justify-center rounded-lg border border-dashed border-[var(--border)] bg-[var(--surface-raised)] p-6 text-center"
      >
        {!available && (
          <div
            role="alert"
            className="mb-3 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300"
          >
            Agent tools are unavailable. Showing partial results.
          </div>
        )}
        <p className="text-sm text-[var(--text-muted)]">
          No evidence yet. Ask a question to see tool calls and sources.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="evidence-panel" data-tour="agent-evidence" className="space-y-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        Evidence
      </h3>

      {!available && (
        <div
          role="alert"
          className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300"
        >
          Agent tools are unavailable. Showing partial results.
        </div>
      )}

      <div className="space-y-2">
        {toolCalls.map((tc, i) => (
          <ToolCallCard key={i} toolCall={tc} index={i} />
        ))}
      </div>

      <ProvenanceGrid toolCalls={toolCalls} />
    </div>
  );
}