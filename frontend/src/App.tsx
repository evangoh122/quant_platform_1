import { useState, useEffect, useCallback } from 'react';
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
import { BusinessCaseOverview } from './screens/BusinessCaseOverview';
import { BusinessCaseData } from './screens/BusinessCaseData';
import { BusinessCaseInfrastructure } from './screens/BusinessCaseInfrastructure';
import { BusinessCaseFeatures } from './screens/BusinessCaseFeatures';
import { BusinessCaseControls } from './screens/BusinessCaseControls';
import { BusinessCaseRubric } from './screens/BusinessCaseRubric';
import { NAV_LINKS } from './data/businessCase';
import { useTourHost, CoachMarks } from './components/tours/TourHost';

type ScreenId =
  | 'platform-overview'
  | 'market'
  | 'options'
  | 'sec'
  | 'agent'
  | 'signals'
  | 'strategy-lab'
  | 'portfolio'
  | 'orders'
  | 'analytics'
  | 'health'
  | 'architecture'
  | 'business-case-overview'
  | 'business-case-data'
  | 'business-case-infrastructure'
  | 'business-case-features'
  | 'business-case-controls'
  | 'business-case-rubric';

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
  {
    label: 'Business Case',
    items: [
      { id: 'business-case-overview', label: NAV_LINKS.overview },
      { id: 'business-case-data', label: NAV_LINKS.data },
      { id: 'business-case-infrastructure', label: NAV_LINKS.infrastructure },
      { id: 'business-case-features', label: NAV_LINKS.features },
      { id: 'business-case-controls', label: NAV_LINKS.controls },
      { id: 'business-case-rubric', label: NAV_LINKS.rubric },
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
  const handleNavigate = useCallback((id: string) => setScreen(id as ScreenId), []);
  const { activeTour, steps, closeTour, handleTourNavigate } = useTourHost(screen, handleNavigate);

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
      case 'business-case-overview':
        return <BusinessCaseOverview onNavigate={(id) => setScreen(id as ScreenId)} />;
      case 'business-case-data':
        return <BusinessCaseData onNavigate={(id) => setScreen(id as ScreenId)} />;
      case 'business-case-infrastructure':
        return <BusinessCaseInfrastructure onNavigate={(id) => setScreen(id as ScreenId)} />;
      case 'business-case-features':
        return <BusinessCaseFeatures onNavigate={(id) => setScreen(id as ScreenId)} />;
      case 'business-case-controls':
        return <BusinessCaseControls onNavigate={(id) => setScreen(id as ScreenId)} />;
      case 'business-case-rubric':
        return <BusinessCaseRubric onNavigate={(id) => setScreen(id as ScreenId)} />;
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
      <CoachMarks steps={steps} run={!!activeTour} onClose={closeTour} onNavigate={handleTourNavigate} currentScreen={screen} />
    </>
  );
}