import { useEffect, useRef } from 'react';

interface SuccessToastProps {
  message: string;
  onDismiss: () => void;
  autoMs?: number;
}

export function SuccessToast({ message, onDismiss, autoMs = 4000 }: SuccessToastProps) {
  const dismissRef = useRef(onDismiss);
  dismissRef.current = onDismiss;

  useEffect(() => {
    const timer = setTimeout(() => dismissRef.current(), autoMs);
    return () => clearTimeout(timer);
  }, [autoMs]);

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 flex items-center gap-3 rounded-[var(--radius-md)] border border-[var(--positive)]/20 bg-[var(--surface)] px-4 py-3 text-sm shadow-lg"
    >
      <span className="text-[var(--positive)]" aria-hidden="true">✓</span>
      <span className="text-[var(--text-primary)]">{message}</span>
      <button
        onClick={onDismiss}
        className="ml-2 text-[var(--text-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2"
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  );
}