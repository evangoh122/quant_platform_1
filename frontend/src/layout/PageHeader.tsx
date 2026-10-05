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

export function PageHeader({ currentId, groups, onMenuToggle, onTour }: PageHeaderProps) {
  const label = findLabel(currentId, groups);

  return (
    <header className="flex items-center justify-between border-b border-[var(--border)] bg-[var(--surface)] px-[var(--space-6)] py-[var(--space-3)]">
      <div className="flex items-center gap-3 pl-10 lg:pl-0">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">{label}</h1>
      </div>

      <div className="flex items-center gap-2">
        <button
          data-tour="tour-action"
          onClick={onTour}
          className="rounded-[var(--radius-sm)] border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-raised)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2"
        >
          Take a tour
        </button>
      </div>
    </header>
  );
}