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
        onClick={onToggle}
        className="fixed left-4 top-3 z-40 rounded-[var(--radius-sm)] p-2 text-[var(--text-primary)] hover:bg-[var(--surface-raised)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
        aria-label={open ? 'Close navigation' : 'Open navigation'}
        aria-expanded={open}
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
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            onKeyDown={handleTrapFocus}
            className="absolute inset-y-0 left-0 w-[min(80vw,320px)] overflow-y-auto bg-[var(--surface)] shadow-xl"
          >
            <div className="border-b border-[var(--border)] px-4 py-4 pl-14">
              <div className="text-sm font-bold text-[var(--text-primary)]">QP1</div>
              <div className="text-xs text-[var(--text-muted)]">Quant Trading Platform</div>
            </div>

            <nav className="p-2">
              {groups.map((group) => (
                <div key={group.label} className="mb-2">
                  <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                    {group.label}
                  </div>
                  {group.items.map((item) => {
                    const active = item.id === currentId;
                    return (
                      <button
                        key={item.id}
                        onClick={() => onNavigate(item.id)}
                        aria-current={active ? 'page' : undefined}
                        className={`block w-full rounded-[var(--radius-sm)] px-3 py-2 text-left text-sm transition-colors ${
                          active
                            ? 'bg-[var(--accent)] font-medium text-white'
                            : 'text-[var(--text-secondary)] hover:bg-[var(--surface-raised)]'
                        }`}
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