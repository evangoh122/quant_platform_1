import type { ToolCall, ChatResponse } from '../api/types';

export type TraceStage = 'retrieval' | 'tool_execution' | 'response';

export interface TraceStep {
  stage: TraceStage;
  label: string;
  status: 'pending' | 'running' | 'complete' | 'failed' | 'skipped';
}

function deriveSteps(toolCalls: ToolCall[], _available: boolean, reply?: string): TraceStep[] {
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
    ? 'pending'
    : hasWrite
      ? writeFailed
        ? 'failed'
        : 'complete'
      : anyFailed
        ? 'failed'
        : 'complete';

  // Response stage uses reply-delivered signal, not `available`:
  // - sending with no reply → pending
  // - reply delivered (even empty tools) → complete
  // - finished, no reply, not sending → failed
  const responseStatus: TraceStep['status'] = hasReply
    ? 'complete'
    : toolCalls.length > 0 && !hasReply
      ? 'failed'
      : 'pending';

  return [
    { stage: 'retrieval', label: 'Retrieval', status: retrievalStatus },
    { stage: 'tool_execution', label: 'Tool execution', status: toolStatus },
    { stage: 'response', label: 'Response', status: responseStatus },
  ];
}

const STATUS_STYLES: Record<TraceStep['status'], string> = {
  pending: 'bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-400',
  running: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  complete: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  failed: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  skipped: 'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500',
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
}

export function ExecutionTrace({ toolCalls, available, sending, reply }: ExecutionTraceProps) {
  const steps = deriveSteps(toolCalls, available, reply);

  if (toolCalls.length === 0 && !sending) return null;

  return (
    <div data-testid="execution-trace" className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
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
              <span className="text-slate-700 dark:text-slate-300">{step.label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}