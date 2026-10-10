import { useState, useCallback, type ReactNode } from 'react';
import type { HealthResponse } from '../api/types';
import { Sidebar } from './Sidebar';
import { MobileNavigation } from './MobileNavigation';
import { PageHeader } from './PageHeader';
import { StatusBanner } from './StatusBanner';

export interface NavGroup {
  label: string;
  items: { id: string; label: string }[];
}

interface AppShellProps {
  groups: NavGroup[];
  currentId: string;
  onNavigate: (id: string) => void;
  health: HealthResponse | null;
  children: ReactNode;
}

export function AppShell({ groups, currentId, onNavigate, health, children }: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleNavigate = useCallback((id: string) => {
    onNavigate(id);
    setMobileOpen(false);
  }, [onNavigate]);

  const handleToggleMobile = useCallback(() => {
    setMobileOpen((v) => !v);
  }, []);

  const handleCloseMobile = useCallback(() => {
    setMobileOpen(false);
  }, []);

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen((v) => !v);
  }, []);

  const handleTour = useCallback(() => {
    const tour = currentId === 'agent' ? 'agent' : currentId === 'architecture' ? 'architecture' : 'application';
    window.dispatchEvent(new CustomEvent('qp-tour-request', { detail: { tour } }));
  }, [currentId]);

  const lakebaseDown = health?.dependencies.some(
    (d) => d.name === 'lakebase' && (!d.ok || d.circuit_breaker_state === 'open'),
  ) ?? false;

  return (
    <div className="flex min-h-screen bg-[var(--canvas)] text-[var(--text-primary)]">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[9999] focus:rounded-[var(--radius-sm)] focus:bg-[var(--accent)] focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-[var(--accent-ink)] focus:shadow-lg"
      >
        Skip to main content
      </a>
      <div {...(mobileOpen ? { inert: '', 'aria-hidden': true } : {})}>
        <Sidebar
          groups={groups}
          currentId={currentId}
          onNavigate={handleNavigate}
          collapsed={!sidebarOpen}
          onToggle={handleToggleSidebar}
        />
      </div>

      <MobileNavigation
        groups={groups}
        currentId={currentId}
        onNavigate={handleNavigate}
        open={mobileOpen}
        onToggle={handleToggleMobile}
        onClose={handleCloseMobile}
      />

      <div {...(mobileOpen ? { inert: '', 'aria-hidden': true } : {})} className="flex min-w-0 flex-1 flex-col">
        <PageHeader
          currentId={currentId}
          groups={groups}
          onMenuToggle={handleToggleMobile}
          onTour={handleTour}
        />

        <main id="main-content" tabIndex={-1} className="min-w-0 flex-1 p-[var(--space-6)]">
          <StatusBanner lakebaseDown={lakebaseDown} />
          {children}
        </main>
      </div>
    </div>
  );
}