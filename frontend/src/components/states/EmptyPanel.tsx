interface EmptyPanelProps {
  title: string;
  detail?: string;
  action?: { label: string; onClick: () => void };
}

export function EmptyPanel({ title, detail, action }: EmptyPanelProps) {
  return (
    <div
      role="status"
      aria-label={title}
      className="flex flex-col items-center justify-center rounded-[var(--radius-md)] border border-dashed border-[var(--border)] bg-[var(--surface)] px-6 py-10 text-center"
    >
      <p className="text-sm font-medium text-[var(--text-primary)]">{title}</p>
      {detail && (
        <p className="mt-1 max-w-md text-xs text-[var(--text-secondary)]">{detail}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-4 rounded-[var(--radius-sm)] bg-[var(--accent)] px-4 py-2 text-xs font-medium text-white hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}