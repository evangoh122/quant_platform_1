import type { ToolCall, ChatResponse } from '../api/types';

export type TraceStage = 'retrieval' | 'tool_execution' | 'response';

export interface TraceStep {
  stage: TraceStage;
  label: string;
  status: 'pending' | 'running' | 'complete' | 'failed' | 'skipped';
}

function deriveSteps(toolCalls: ToolCall[], _available: boolean, reply?: string, sending = false): TraceStep[] {
  const retrievalTools = toolCalls.filter(
    (tc) => tc.name === 'search_sec_filings' || tc.name === 'get_latest_signal',
  );
  const writeTools = toolCalls.filter(
    (tc) => tc.name === 'save_research_note' || tc.name === 'add_to_watchlist',
  );
  const hasRetrieval = retrievalTools.length > 0;
  const hasWrite = writeTools.length > 0;
  const retrievalFailed = retrievalTools.some((tc) => !tc.ok);
  const writeFailed = writeTools.some((tc) => !tc.ok);
  const anyFailed = toolCalls.some((tc) => !tc.ok);
  const hasReply = typeof reply === 'string' && reply.length > 0;

  const retrievalStatus: TraceStep['status'] = !hasRetrieval
    ? 'skipped'
    : retrievalFailed
      ? 'failed'
      : 'complete';

  const toolStatus: TraceStep['status'] = toolCalls.length === 0
    ? hasReply
      ? 'skipped'
      : 'pending'
    : hasWrite
      ? writeFailed
        ? 'failed'
        : 'complete'
      : anyFailed
        ? 'failed'
        : 'complete';

  // Response stage uses reply-delivered signal, not `available`:
  // - sending with no reply → pending
  // - reply delivered (even zero tools) → complete
  // - finished, no reply → failed
  const responseStatus: TraceStep['status'] = hasReply
    ? 'complete'
    : !sending
      ? 'failed'
      : 'pending';

  return [
    { stage: 'retrieval', label: 'Retrieval', status: retrievalStatus },
    { stage: 'tool_execution', label: 'Tool execution', status: toolStatus },
    { stage: 'response', label: 'Response', status: responseStatus },
  ];
}

const STATUS_STYLES: Record<TraceStep['status'], string> = {
  pending: 'bg-[var(--surface-raised)] text-[var(--text-muted)]',
  running: 'bg-info-dim text-[var(--info)]',
  complete: 'bg-positive-dim text-[var(--positive)]',
  failed: 'bg-negative-dim text-[var(--negative)]',
  skipped: 'bg-[var(--surface-raised)] text-[var(--text-muted)]',
};

const STATUS_LABELS: Record<TraceStep['status'], string> = {
  pending: 'Pending',
  running: 'Running',
  complete: 'Complete',
  failed: 'Failed',
  skipped: 'Skipped',
};

interface ExecutionTraceProps {
  toolCalls: ToolCall[];
  available: boolean;
  sending: boolean;
  reply?: string;
  attempted?: boolean;
}

export function ExecutionTrace({ toolCalls, available, sending, reply, attempted }: ExecutionTraceProps) {
  const steps = deriveSteps(toolCalls, available, reply, sending);

  if (toolCalls.length === 0 && !sending && !reply && !attempted) return null;

  return (
    <div data-testid="execution-trace" className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        Execution
      </h3>
      <ol className="space-y-1">
        {steps.map((step) => {
          const effectiveStatus =
            sending && step.status === 'pending' ? 'running' : step.status;
          return (
            <li key={step.stage} className="flex items-center gap-2 text-xs">
              <span
                data-testid={`trace-${step.stage}`}
                className={`inline-flex items-center rounded-full px-2 py-0.5 font-medium ${STATUS_STYLES[effectiveStatus]}`}
              >
                {STATUS_LABELS[effectiveStatus]}
              </span>
              <span className="text-[var(--text-secondary)]">{step.label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}