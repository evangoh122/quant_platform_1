import { useState, useEffect } from 'react';
import { api } from './api/client';
import type { HealthResponse } from './api/types';
import { MarketDashboard } from './screens/MarketDashboard';
import { SignalExplorer } from './screens/SignalExplorer';
import { OptionsAnalytics } from './screens/OptionsAnalytics';
import { SecFilingExplorer } from './screens/SecFilingExplorer';
import { ResearchAgent } from './screens/ResearchAgent';
import { PaperPortfolio } from './screens/PaperPortfolio';
import { OrderApprovalDrawer } from './screens/OrderApprovalDrawer';
import { SystemHealth } from './screens/SystemHealth';

type ScreenId =
  | 'market'
  | 'signals'
  | 'options'
  | 'sec'
  | 'agent'
  | 'portfolio'
  | 'orders'
  | 'health';

const SCREENS: { id: ScreenId; label: string }[] = [
  { id: 'market', label: 'Market Dashboard' },
  { id: 'signals', label: 'Signal Explorer' },
  { id: 'options', label: 'Options Analytics' },
  { id: 'sec', label: 'SEC Filing Explorer' },
  { id: 'agent', label: 'AI Research Agent' },
  { id: 'portfolio', label: 'IBKR Paper Portfolio' },
  { id: 'orders', label: 'Order Approval' },
  { id: 'health', label: 'Analytics / System Health' },
];

export default function App() {
  const [screen, setScreen] = useState<ScreenId>('market');
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);

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

  const lakebaseDown = healthData?.dependencies.some(
    (d) => d.name === 'lakebase' && (!d.ok || d.circuit_breaker_state === 'open'),
  ) ?? false;

  return (
    <div className="flex min-h-screen bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <aside className="w-56 shrink-0 border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="border-b border-slate-200 px-4 py-4 dark:border-slate-800">
          <div className="text-sm font-bold">QP1</div>
          <div className="text-xs text-slate-500 dark:text-slate-400">Quant Trading Platform</div>
        </div>
        <nav className="p-2">
          {SCREENS.map((s) => (
            <button
              key={s.id}
              onClick={() => setScreen(s.id)}
              className={`block w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                screen === s.id
                  ? 'bg-slate-900 font-medium text-white dark:bg-slate-100 dark:text-slate-900'
                  : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              {s.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="min-w-0 flex-1 p-6">
        {lakebaseDown && (
          <div className="mb-4 rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-200">
            Account services unavailable — write operations (orders, watchlists) are disabled. Read-only data is still accessible.
          </div>
        )}
        {screen === 'market' && <MarketDashboard />}
        {screen === 'signals' && <SignalExplorer />}
        {screen === 'options' && <OptionsAnalytics />}
        {screen === 'sec' && <SecFilingExplorer />}
        {screen === 'agent' && <ResearchAgent />}
        {screen === 'portfolio' && <PaperPortfolio />}
        {screen === 'orders' && <OrderApprovalDrawer />}
        {screen === 'health' && <SystemHealth />}
      </main>
    </div>
  );
}
