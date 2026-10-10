interface ErrorPanelProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorPanel({ title = 'Something went wrong', message, onRetry }: ErrorPanelProps) {
  return (
    <div
      role="alert"
      className="rounded-[var(--radius-md)] border border-negative-dim-20 bg-negative-dim-5 px-6 py-8 text-center"
    >
      <p className="text-sm font-medium text-[var(--negative)]">{title}</p>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 rounded-[var(--radius-sm)] bg-[var(--danger-fill)] px-4 py-2 text-xs font-medium text-[var(--on-danger)] hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--negative)] focus-visible:ring-offset-2"
        >
          Retry
        </button>
      )}
    </div>
  );
}