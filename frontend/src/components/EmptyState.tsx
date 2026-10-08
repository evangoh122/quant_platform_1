interface EmptyStateProps {
  title: string;
  detail?: string;
}

export function EmptyState({ title, detail }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-[var(--radius-md)] border border-dashed border-[var(--border)] bg-[var(--surface)] px-4 py-8 text-center">
      <p className="text-sm font-medium text-[var(--text-secondary)]">{title}</p>
      {detail && <p className="mt-1 max-w-md text-xs text-[var(--text-muted)]">{detail}</p>}
    </div>
  );
}
