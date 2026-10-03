import type { Freshness } from '../api/types';

const STATE_STYLES: Record<Freshness['state'], string> = {
  fresh: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  stale: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  empty: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  unavailable: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
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
