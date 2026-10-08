interface StatusBannerProps {
  lakebaseDown: boolean;
}

export function StatusBanner({ lakebaseDown }: StatusBannerProps) {
  if (!lakebaseDown) return null;

  return (
    <div
      data-tour="lakebase-banner"
      role="alert"
      className="mb-4 rounded-[var(--radius-md)] border border-[var(--negative)]/20 bg-[var(--negative)]/5 px-4 py-3 text-sm text-[var(--negative)]"
    >
      Account services unavailable — write operations (orders, watchlists) are disabled. Read-only data is still accessible.
    </div>
  );
}