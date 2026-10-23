import type { NavGroup } from './AppShell';

interface SidebarProps {
  groups: NavGroup[];
  currentId: string;
  onNavigate: (id: string) => void;
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ groups, currentId, onNavigate, collapsed, onToggle }: SidebarProps) {
  return (
    <aside
      data-tour="navigation"
      className={`hidden lg:flex shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] transition-[width] duration-200 ${
        collapsed ? 'w-16' : 'w-56'
      }`}
    >
      {/* Navigation-only. The one brand mark lives in the top bar, so the
          sidebar never repeats it: exactly one brand presentation per view. */}
      <div className={`flex items-center border-b border-[var(--border)] px-4 py-4 ${collapsed ? 'justify-center' : 'justify-end'}`}>
        <button
          onClick={onToggle}
          className="control-target shrink-0 rounded-[var(--radius-sm)] p-1 text-[var(--text-muted)] hover:bg-[var(--surface-raised)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
        >
          {collapsed ? '→' : '←'}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto p-2">
        {groups.map((group) => (
          <div key={group.label} className="mb-2">
            {!collapsed && (
              /* Uppercase tracked group label kept from the original shell, but
                 at 13 px (text-xs) instead of 10 px: 12 px is the floor for
                 labels, 13 px the repo's caption size. */
              <div className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                {group.label}
              </div>
            )}
            {group.items.map((item) => {
              const active = item.id === currentId;
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  aria-current={active ? 'page' : undefined}
                  aria-label={collapsed ? item.label : undefined}
                  className={`nav-item ${active ? 'active' : ''} ${collapsed ? 'justify-center' : ''}`}
                  title={collapsed ? item.label : undefined}
                >
                  {collapsed ? item.label.charAt(0) : item.label}
                </button>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
