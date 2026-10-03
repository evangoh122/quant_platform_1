interface EmptyStateProps {
  title: string;
  detail?: string;
}

export function EmptyState({ title, detail }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center dark:border-slate-700 dark:bg-slate-800/50">
      <p className="text-sm font-medium text-slate-600 dark:text-slate-300">{title}</p>
      {detail && <p className="mt-1 max-w-md text-xs text-slate-500 dark:text-slate-400">{detail}</p>}
    </div>
  );
}
