interface StaleDataNoticeProps {
  table: string;
  detail?: string;
  onRefresh?: () => void;
}

export function StaleDataNotice({ table, detail, onRefresh }: StaleDataNoticeProps) {
  return (
    <div
      role="status"
      aria-label="Stale data"
      className="flex items-center justify-between rounded-[var(--radius-sm)] border border-[var(--warning)]/20 bg-[var(--warning)]/5 px-4 py-2 text-xs"
    >
      <span className="text-[var(--warning)]">
        {table} data may be outdated{detail ? ` — ${detail}` : ''}
      </span>
      {onRefresh && (
        <button
          onClick={onRefresh}
          className="ml-3 shrink-0 rounded-[var(--radius-sm)] border border-[var(--warning)]/30 px-2 py-1 font-medium text-[var(--warning)] hover:bg-[var(--warning)]/10 focus-visible:ring-2 focus-visible:ring-[var(--warning)] focus-visible:ring-offset-2"
        >
          Refresh
        </button>
      )}
    </div>
  );
}