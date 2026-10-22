import { useEffect, useRef, useCallback } from 'react';
import type { NavGroup } from './AppShell';

interface MobileNavigationProps {
  groups: NavGroup[];
  currentId: string;
  onNavigate: (id: string) => void;
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
}

export function MobileNavigation({ groups, currentId, onNavigate, open, onToggle, onClose }: MobileNavigationProps) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (open && drawerRef.current) {
      const firstButton = drawerRef.current.querySelector('button');
      firstButton?.focus();
    }
  }, [open]);

  useEffect(() => {
    if (wasOpen.current && !open && triggerRef.current) {
      triggerRef.current.focus();
    }
    wasOpen.current = open;
  }, [open]);

  const handleTrapFocus = useCallback((e: React.KeyboardEvent) => {
    if (e.key !== 'Tab' || !drawerRef.current) return;
    const focusable = drawerRef.current.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }, []);

  return (
    <div className="lg:hidden">
      <button
        ref={triggerRef}
        data-tour="mobile-menu"
        onClick={onToggle}
        className="control-target fixed left-4 top-3 z-40 rounded-[var(--radius-sm)] p-2 text-[var(--text-primary)] hover:bg-[var(--surface-raised)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
        aria-label={open ? 'Close navigation' : 'Open navigation'}
        aria-expanded={open}
        aria-controls="mobile-nav-drawer"
      >
        {open ? '✕' : '☰'}
      </button>

      {open && (
        <div className="fixed inset-0 z-30">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={onClose}
            aria-hidden="true"
          />
          <div
            ref={drawerRef}
            id="mobile-nav-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            onKeyDown={handleTrapFocus}
            className="absolute inset-y-0 left-0 w-[min(80vw,320px)] max-w-full overflow-y-auto bg-[var(--surface)] shadow-xl"
          >
            {/* Navigation-only: the brand mark lives in the top bar, so the
                drawer never carries a second tile and the two can never show
                at once. This spacer keeps the first group clear of the fixed
                menu trigger that overlaps the drawer's top-left corner. */}
            <div className="h-16 border-b border-[var(--border)]" aria-hidden="true" />

            <nav className="p-2">
              {groups.map((group) => (
                <div key={group.label} className="mb-2">
                  <div className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                    {group.label}
                  </div>
                  {group.items.map((item) => {
                    const active = item.id === currentId;
                    return (
                      <button
                        key={item.id}
                        onClick={() => onNavigate(item.id)}
                        aria-current={active ? 'page' : undefined}
                        className={`nav-item ${active ? 'active' : ''}`}
                      >
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              ))}
            </nav>
          </div>
        </div>
      )}
    </div>
  );
}