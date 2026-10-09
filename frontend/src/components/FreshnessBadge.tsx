import type { Freshness } from '../api/types';

const STATE_STYLES: Record<Freshness['state'], string> = {
  fresh: 'bg-[var(--positive)]/15 text-[var(--positive)]',
  stale: 'bg-[var(--warning)]/15 text-[var(--warning)]',
  empty: 'bg-[var(--surface-raised)] text-[var(--text-muted)]',
  unavailable: 'bg-[var(--negative)]/15 text-[var(--negative)]',
};

export function FreshnessBadge({ freshness }: { freshness: Freshness }) {
  const label = freshness.state === 'unavailable' ? 'unavailable' : `${freshness.state} · ${freshness.table}`;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${STATE_STYLES[freshness.state]}`}
      title={freshness.detail}
    >
      {label}
    </span>
  );
}
