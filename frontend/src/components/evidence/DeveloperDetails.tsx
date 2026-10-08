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
      <summary className="cursor-pointer text-[11px] font-medium text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300">
        Developer details
      </summary>
      <div className="mt-1 space-y-2 rounded-md bg-slate-50 p-2 text-[11px] dark:bg-slate-800">
        <div>
          <span className="font-semibold text-slate-600 dark:text-slate-400">Arguments</span>
          <pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap break-all text-slate-500 dark:text-slate-400">
            {JSON.stringify(args, null, 2)}
          </pre>
        </div>
        <div>
          <span className="font-semibold text-slate-600 dark:text-slate-400">Result</span>
          <pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap break-all text-slate-500 dark:text-slate-400">
            {result ? JSON.stringify(result, null, 2) : 'null'}
          </pre>
        </div>
      </div>
    </details>
  );
}