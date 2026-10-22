interface StatTileProps {
  label: string;
  value: string;
  hint?: string;
}

export function StatTile({ label, value, hint }: StatTileProps) {
  return (
    <div className="stat-card">
      <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </div>
      <div className="break-anywhere mt-1 text-lg font-semibold text-[var(--text-primary)]">{value}</div>
      {hint && <div className="break-anywhere mt-0.5 text-xs text-[var(--text-muted)]">{hint}</div>}
    </div>
  );
}
