import type { NavGroup } from './AppShell';

interface PageHeaderProps {
  currentId: string;
  groups: NavGroup[];
  onMenuToggle: () => void;
  onTour: () => void;
}

function findLabel(id: string, groups: NavGroup[]): string {
  for (const group of groups) {
    for (const item of group.items) {
      if (item.id === id) return item.label;
    }
  }
  return '';
}

/**
 * Top bar, adapted from the site's navigation: a gold monogram tile with the
 * product name on the left, the current screen next to it, and quiet icon +
 * label actions on the right. The sidebar stays the primary navigation, so
 * this bar never carries the full link set. This monogram is the one brand
 * mark per view: the sidebar and the mobile drawer are navigation-only and
 * never repeat it.
 */
export function PageHeader({ currentId, groups, onMenuToggle, onTour }: PageHeaderProps) {
  const label = findLabel(currentId, groups);
  const env = import.meta.env.MODE === 'production' ? 'prod' : import.meta.env.MODE === 'staging' ? 'staging' : 'dev';

  return (
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-[var(--border)] bg-[var(--surface)] py-[var(--space-3)] pl-14 pr-4 sm:pr-6 lg:pl-6">
      <div className="flex min-w-0 items-center gap-3">
        <span className="brand-tile" aria-hidden="true">
          Q
        </span>
        <div className="hidden min-w-0 sm:block">
          <p className="text-sm font-semibold leading-tight text-[var(--text-primary)]">QP1</p>
          <p className="text-xs leading-tight text-[var(--text-muted)]">Quant research</p>
        </div>
        <span className="hidden h-6 w-px shrink-0 bg-[var(--border)] sm:block" aria-hidden="true" />
        <div className="flex min-w-0 items-center gap-2">
          <h1 className="truncate text-lg font-semibold text-[var(--text-primary)]">{label}</h1>
          <span
            data-testid="env-badge"
            className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium ${
              env === 'prod'
                ? 'bg-positive-dim text-[var(--positive)]'
                : env === 'staging'
                  ? 'bg-warning-dim text-[var(--warning)]'
                  : 'bg-[var(--surface-raised)] text-[var(--text-muted)]'
            }`}
          >
            {env}
          </span>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <button
          data-tour="tour-action"
          onClick={onTour}
          className="control-target inline-flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition hover:border-[var(--accent)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2"
        >
          <span aria-hidden="true">&#9678;</span>
          <span className="whitespace-nowrap">Take a tour</span>
        </button>
      </div>
    </header>
  );
}
