import { useId } from 'react';

export interface NavItem {
  id: string;
  label: string;
  disabled?: boolean;
}

interface NavItemButtonProps {
  item: NavItem;
  active: boolean;
  collapsed?: boolean;
  onNavigate: (id: string) => void;
}

/**
 * Sidebar/drawer entry. Disabled entries stay focusable (unlike the native
 * `disabled` attribute) so the "Coming soon" hint can be reached by keyboard
 * and announced through aria-describedby; activation is suppressed instead.
 */
export function NavItemButton({ item, active, collapsed = false, onNavigate }: NavItemButtonProps) {
  const hintId = useId();
  const content = collapsed ? item.label.charAt(0) : item.label;

  if (item.disabled) {
    return (
      <>
        <button
          type="button"
          aria-disabled="true"
          aria-describedby={hintId}
          aria-label={collapsed ? `${item.label} — Coming soon` : undefined}
          title={collapsed ? `${item.label} — Coming soon` : undefined}
          className={`nav-item nav-item-disabled ${collapsed ? 'justify-center' : ''}`}
          onClick={(event) => event.preventDefault()}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') event.preventDefault();
          }}
        >
          {content}
        </button>
        <span id={hintId} className="sr-only">Coming soon</span>
      </>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onNavigate(item.id)}
      aria-current={active ? 'page' : undefined}
      aria-label={collapsed ? item.label : undefined}
      className={`nav-item ${active ? 'active' : ''} ${collapsed ? 'justify-center' : ''}`}
      title={collapsed ? item.label : undefined}
    >
      {content}
    </button>
  );
}
