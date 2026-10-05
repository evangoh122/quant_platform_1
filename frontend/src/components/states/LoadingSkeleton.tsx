interface LoadingSkeletonProps {
  rows?: number;
  className?: string;
}

export function LoadingSkeleton({ rows = 3, className = '' }: LoadingSkeletonProps) {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={`space-y-2 ${className}`}
    >
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded-[var(--radius-sm)] bg-[var(--surface-raised)]"
          style={{ width: `${85 - i * 10}%` }}
        />
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}