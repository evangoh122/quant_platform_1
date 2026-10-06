import { useState, useEffect } from 'react';
import { api } from './api/client';
import type { HealthResponse } from './api/types';
import { AppShell, type NavGroup } from './layout/AppShell';
import { MarketDashboard } from './screens/MarketDashboard';
import { SignalExplorer } from './screens/SignalExplorer';
import { OptionsAnalytics } from './screens/OptionsAnalytics';
import { SecFilingExplorer } from './screens/SecFilingExplorer';
import { ResearchAgent } from './screens/ResearchAgent';
import { PaperPortfolio } from './screens/PaperPortfolio';
import { OrderApprovalDrawer } from './screens/OrderApprovalDrawer';
import { SystemHealth } from './screens/SystemHealth';
import { PlatformOverview } from './screens/PlatformOverview';
import { ArchitectureEvidence } from './screens/ArchitectureEvidence';
import { Positioning } from './screens/Positioning';
import { useTourHost, CoachMarks } from './components/tours/TourHost';

type ScreenId =
  | 'platform-overview'
  | 'market'
  | 'options'
  | 'positioning'
  | 'sec'
  | 'agent'
  | 'signals'
  | 'strategy-lab'
  | 'portfolio'
  | 'orders'
  | 'analytics'
  | 'health'
  | 'architecture';

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Overview',
    items: [{ id: 'platform-overview', label: 'Platform Overview' }],
  },
  {
    label: 'Research',
    items: [
      { id: 'market', label: 'Market Explorer' },
      { id: 'options', label: 'Options Analytics' },
      { id: 'positioning', label: 'Positioning' },
      { id: 'sec', label: 'SEC Research' },
      { id: 'agent', label: 'AI Research Agent' },
    ],
  },
  {
    label: 'Strategy',
    items: [
      { id: 'signals', label: 'Signal Explorer' },
      { id: 'strategy-lab', label: 'Strategy Lab' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { id: 'portfolio', label: 'Paper Portfolio' },
      { id: 'orders', label: 'Order Approval' },
    ],
  },
  {
    label: 'Evidence',
    items: [
      { id: 'analytics', label: 'Activity Analytics' },
      { id: 'health', label: 'System Health' },
      { id: 'architecture', label: 'Architecture & Tests' },
    ],
  },
];

function PlaceholderScreen({ title, tourId }: { title: string; tourId?: string }) {
  return (
    <div data-tour={tourId} className="flex flex-col items-center justify-center rounded-[var(--radius-md)] border border-dashed border-[var(--border)] bg-[var(--surface)] px-6 py-16 text-center">
      <p className="text-lg font-semibold text-[var(--text-primary)]">{title}</p>
      <p className="mt-1 text-sm text-[var(--text-muted)]">Coming in a future delivery round.</p>
    </div>
  );
}

export default function App() {
  const [screen, setScreen] = useState<ScreenId>('platform-overview');
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const { activeTour, steps, closeTour } = useTourHost();

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      api.health().then((d) => {
        if (!cancelled) setHealthData(d);
      }).catch(() => {
        // Silently ignore health check failures
      });
    };
    check();
    const interval = setInterval(check, 30_000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  const renderScreen = () => {
    switch (screen) {
      case 'platform-overview':
        return <PlatformOverview onNavigate={(id) => setScreen(id as ScreenId)} />;
      case 'market':
        return <MarketDashboard />;
      case 'options':
        return <OptionsAnalytics />;
      case 'positioning':
        return <Positioning />;
      case 'sec':
        return <SecFilingExplorer />;
      case 'agent':
        return <ResearchAgent />;
      case 'signals':
        return <SignalExplorer />;
      case 'strategy-lab':
        return <PlaceholderScreen title="Strategy Lab" />;
      case 'portfolio':
        return <PaperPortfolio />;
      case 'orders':
        return <OrderApprovalDrawer />;
      case 'analytics':
        return <PlaceholderScreen title="Activity Analytics" />;
      case 'health':
        return <SystemHealth />;
      case 'architecture':
        return <ArchitectureEvidence />;
      default:
        return <PlaceholderScreen title="Platform Overview" />;
    }
  };

  return (
    <>
      <AppShell
        groups={NAV_GROUPS}
        currentId={screen}
        onNavigate={(id) => setScreen(id as ScreenId)}
        health={healthData}
      >
        {renderScreen()}
      </AppShell>
      <CoachMarks steps={steps} run={!!activeTour} onClose={closeTour} />
    </>
  );
}