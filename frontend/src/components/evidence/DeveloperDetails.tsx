import { useState } from 'react';

interface DeveloperDetailsProps {
  arguments: Record<string, unknown>;
  result: Record<string, unknown> | null;
}

export function DeveloperDetails({ arguments: args, result }: DeveloperDetailsProps) {
  const [open, setOpen] = useState(false);

  return (
    <details
      data-testid="developer-details"
      className="mt-2"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer text-[11px] font-medium text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
        Developer details
      </summary>
      <div className="mt-1 space-y-2 rounded-md bg-[var(--surface-raised)] p-2 text-[11px]">
        <div>
          <span className="font-semibold text-[var(--text-secondary)]">Arguments</span>
          <pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap break-all text-[var(--text-muted)]">
            {JSON.stringify(args, null, 2)}
          </pre>
        </div>
        <div>
          <span className="font-semibold text-[var(--text-secondary)]">Result</span>
          <pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap break-all text-[var(--text-muted)]">
            {result ? JSON.stringify(result, null, 2) : 'null'}
          </pre>
        </div>
      </div>
    </details>
  );
}