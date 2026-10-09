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
      <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-4">
        {!collapsed && (
          <div>
            <div className="text-sm font-bold text-[var(--text-primary)]">QP1</div>
            <div className="text-xs text-[var(--text-muted)]">Quant Trading Platform</div>
          </div>
        )}
        <button
          onClick={onToggle}
          className="rounded-[var(--radius-sm)] p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
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
              <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
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