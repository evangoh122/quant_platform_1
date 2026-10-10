interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--negative)] bg-negative-dim px-4 py-6 text-center">
      <p className="text-sm font-medium text-[var(--negative)]">Something went wrong</p>
      <p className="mt-1 text-xs text-[var(--negative)]">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 rounded-[var(--radius-md)] bg-[var(--danger-fill)] px-3 py-1.5 text-xs font-medium text-[var(--on-danger)] hover:opacity-90"
        >
          Retry
        </button>
      )}
    </div>
  );
}
