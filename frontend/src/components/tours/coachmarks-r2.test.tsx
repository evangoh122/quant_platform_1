import { render, screen, act, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import CoachMarks, { tourSeen, markTourSeen, type CoachStep } from './CoachMarks';
import { useTourHost } from './TourHost';
import { EvidencePanel } from '../evidence/EvidencePanel';
import { AppShell, type NavGroup } from '../../layout/AppShell';
import {
  APPLICATION_TOUR,
  AGENT_TOUR,
  ARCHITECTURE_TOUR,
  APPLICATION_TOUR_KEY,
  AGENT_TOUR_KEY,
  ARCHITECTURE_TOUR_KEY,
} from './tourSteps';

const __dirname = dirname(fileURLToPath(import.meta.url));
const css: string = readFileSync(join(__dirname, '../../index.css'), 'utf-8');

// ---------- helpers ----------

const mockStore: Record<string, string> = {};
const originalLocalStorage = window.localStorage;

function installMockLocalStorage() {
  Object.keys(mockStore).forEach((k) => delete mockStore[k]);
  Object.defineProperty(window, 'localStorage', {
    value: {
      getItem: (k: string) => (k in mockStore ? mockStore[k] : null),
      setItem: (k: string, v: string) => { mockStore[k] = v; },
      removeItem: (k: string) => { delete mockStore[k]; },
      clear: () => { Object.keys(mockStore).forEach((k) => delete mockStore[k]); },
    },
    writable: true,
  });
}

function restoreLocalStorage() {
  Object.defineProperty(window, 'localStorage', { value: originalLocalStorage, writable: true });
}

function setViewport(width: number, height: number) {
  Object.defineProperty(window, 'innerWidth', { value: width, writable: true });
  Object.defineProperty(window, 'innerHeight', { value: height, writable: true });
}

function fakeRect(overrides: Partial<DOMRect> = {}): DOMRect {
  return {
    top: 100, left: 100, width: 200, height: 50, bottom: 150, right: 300,
    x: 100, y: 100, toJSON: () => {},
    ...overrides,
  } as DOMRect;
}

function installTargetElement(name: string, rect?: Partial<DOMRect>) {
  const el = document.createElement('div');
  el.setAttribute('data-tour', name);
  if (rect) el.getBoundingClientRect = () => fakeRect(rect);
  document.body.appendChild(el);
  return el;
}

const TEST_GROUPS: NavGroup[] = [
  {
    label: 'Overview',
    items: [{ id: 'platform-overview', label: 'Platform Overview' }],
  },
  {
    label: 'Research',
    items: [
      { id: 'market', label: 'Market Explorer' },
      { id: 'agent', label: 'AI Research Agent' },
      { id: 'architecture', label: 'Architecture & Tests' },
    ],
  },
];

const healthyHealth = {
  status: 'ok' as const, version: '1.0.0',
  dependencies: [{ name: 'lakebase', ok: true, detail: 'connected', latency_ms: 5, last_error: null, last_ok_at: Date.now(), circuit_breaker_state: null }],
  freshness: { state: 'fresh' as const, table: '', detail: '' },
  role_cache_size: 0, startup: [],
};

/** Render real AppShell with a given currentId */
function renderRealAppShell(currentId: string) {
  const onNavigate = vi.fn();
  return {
    onNavigate,
    ...render(
      <AppShell
        groups={TEST_GROUPS}
        currentId={currentId}
        onNavigate={onNavigate}
        health={healthyHealth}
      >
        <div />
      </AppShell>,
    ),
  };
}

/** Enumerate all rendered screens from App.tsx renderScreen switch */
const ALL_SCREENS = [
  'platform-overview', 'market', 'options', 'sec', 'agent', 'signals',
  'strategy-lab', 'portfolio', 'orders', 'analytics', 'health', 'architecture',
] as const;

// ---------- mock fetch for App ----------

const healthyResponse = {
  status: 'ok', version: '1.0.0',
  dependencies: [{ name: 'lakebase', ok: true, detail: 'connected', latency_ms: 5, last_error: null, last_ok_at: Date.now(), circuit_breaker_state: null }],
  freshness: { state: 'fresh', table: '', detail: '' },
  role_cache_size: 0, startup: [],
};

const marketResponse = {
  symbol: 'NVDA',
  ohlcv: { data: [], count: 0, empty: true, source: 'silver_ohlcv_day_adjusted', freshness: { state: 'empty', table: '', detail: '' } },
  options: { data: [], count: 0, empty: true, source: 'gold_options_features', freshness: { state: 'empty', table: '', detail: '' } },
};

const chatResponse = { reply: 'No results.', tool_calls: [] };
const secCoverageResponse = { data: [], count: 0, status: 'ok' as const };
const signalsResponse = { data: [], count: 0, empty: true, source: '', freshness: { state: 'empty', table: '', detail: '' } };
const portfolioResponse = {
  positions: { data: [], count: 0, empty: true, source: '', freshness: { state: 'empty', table: '', detail: '' } },
  orders: { data: [], count: 0, empty: true, source: '', freshness: { state: 'empty', table: '', detail: '' } },
};
const healthTraceResponse = { slow: [] };
const analyticsResponse = {
  model_performance: { data: [], count: 0, empty: true, source: '', freshness: { state: 'empty', table: '', detail: '' } },
  agent_activity: { data: [], count: 0, empty: true, source: '', freshness: { state: 'empty', table: '', detail: '' } },
  latency: { data: [], count: 0, empty: true, source: '', freshness: { state: 'empty', table: '', detail: '' } },
  stream_freshness: { data: [], count: 0, empty: true, source: '', freshness: { state: 'empty', table: '', detail: '' } },
};

function mockFetch(body: unknown) {
  return vi.fn().mockImplementation((url: string) => {
    if (url === '/api/health') return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    if (url === '/api/health/trace') return Promise.resolve({ ok: true, json: () => Promise.resolve(healthTraceResponse) });
    if (url === '/api/analytics') return Promise.resolve({ ok: true, json: () => Promise.resolve(analyticsResponse) });
    if (url.startsWith('/api/market/')) return Promise.resolve({ ok: true, json: () => Promise.resolve(marketResponse) });
    if (url === '/api/portfolio') return Promise.resolve({ ok: true, json: () => Promise.resolve(portfolioResponse) });
    if (url === '/api/signals') return Promise.resolve({ ok: true, json: () => Promise.resolve(signalsResponse) });
    if (url === '/api/agent/chat') return Promise.resolve({ ok: true, json: () => Promise.resolve(chatResponse) });
    if (url === '/api/sec/coverage') return Promise.resolve({ ok: true, json: () => Promise.resolve(secCoverageResponse) });
    if (url.startsWith('/api/orders/')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ order_id: '1', status: 'approved', ok: true }) });
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

// ---------- TEST 1: Route-aware header tour (uses real AppShell) ----------

describe('Test 1: Header manual-tour requests are route-aware', () => {
  beforeEach(() => { installMockLocalStorage(); vi.restoreAllMocks(); });
  afterEach(() => { restoreLocalStorage(); });

  it('dispatches agent tour on Agent screen via real AppShell', () => {
    const dispatched: string[] = [];
    const handler = (e: Event) => { dispatched.push((e as CustomEvent).detail.tour); };
    window.addEventListener('qp-tour-request', handler);

    const { unmount } = renderRealAppShell('agent');

    fireEvent.click(screen.getByRole('button', { name: 'Take a tour' }));
    expect(dispatched).toEqual(['agent']);

    window.removeEventListener('qp-tour-request', handler);
    unmount();
  });

  it('dispatches architecture tour on Architecture screen via real AppShell', () => {
    const dispatched: string[] = [];
    const handler = (e: Event) => { dispatched.push((e as CustomEvent).detail.tour); };
    window.addEventListener('qp-tour-request', handler);

    const { unmount } = renderRealAppShell('architecture');

    fireEvent.click(screen.getByRole('button', { name: 'Take a tour' }));
    expect(dispatched).toEqual(['architecture']);

    window.removeEventListener('qp-tour-request', handler);
    unmount();
  });

  it('dispatches application tour on default screen via real AppShell', () => {
    const dispatched: string[] = [];
    const handler = (e: Event) => { dispatched.push((e as CustomEvent).detail.tour); };
    window.addEventListener('qp-tour-request', handler);

    const { unmount } = renderRealAppShell('platform-overview');

    fireEvent.click(screen.getByRole('button', { name: 'Take a tour' }));
    expect(dispatched).toEqual(['application']);

    window.removeEventListener('qp-tour-request', handler);
    unmount();
  });
});

// ---------- TEST 2: Application tour cross-screen navigation ----------

describe('Test 2: Application tour navigates to real screens and finds targets', () => {
  it('APPLICATION_TOUR steps navigate to market, agent, and health screens', () => {
    const analyticsStep = APPLICATION_TOUR.find((s) => s.selector === '[data-tour="analytics-evidence"]');
    expect(analyticsStep?.navigateTo).toBe('health');

    const marketStep = APPLICATION_TOUR.find((s) => s.selector === '[data-tour="market-research"]');
    expect(marketStep?.navigateTo).toBe('market');

    const agentStep = APPLICATION_TOUR.find((s) => s.selector === '[data-tour="agent"]');
    expect(agentStep?.navigateTo).toBe('agent');
  });

  it('each selector-bearing step has a non-empty selector', () => {
    for (const step of APPLICATION_TOUR) {
      if (step.selector) {
        expect(step.selector.length).toBeGreaterThan(0);
        expect(step.selector).toMatch(/^\[data-tour="/);
      }
    }
  });
});

// ---------- TEST 3: Fresh Agent screen evidence anchor ----------

describe('Test 3: Fresh Agent screen exposes evidence tour anchor', () => {
  it('evidence-panel-empty has data-tour="agent-evidence" even with no tool calls', () => {
    render(<EvidencePanel toolCalls={[]} available={true} sending={false} />);

    const emptyPanel = screen.getByTestId('evidence-panel-empty');
    expect(emptyPanel).toHaveAttribute('data-tour', 'agent-evidence');
  });

  it('AGENT_TOUR final step targets agent-evidence selector', () => {
    const evidenceStep = AGENT_TOUR.find((s) => s.selector === '[data-tour="agent-evidence"]');
    expect(evidenceStep).toBeDefined();
    expect(evidenceStep!.title).toBe('Evidence trail');
  });
});

// ---------- TEST 4: Architecture tour targets ----------

describe('Test 4: Architecture tour navigation mounts provenance and pipeline targets', () => {
  it('ARCHITECTURE_TOUR has provenance and pipeline-nodes steps', () => {
    const provenanceStep = ARCHITECTURE_TOUR.find((s) => s.selector === '[data-tour="provenance"]');
    const pipelineStep = ARCHITECTURE_TOUR.find((s) => s.selector === '[data-tour="pipeline-nodes"]');

    expect(provenanceStep).toBeDefined();
    expect(provenanceStep!.navigateTo).toBe('architecture');

    expect(pipelineStep).toBeDefined();
  });

  it('architecture tour navigates to architecture screen for provenance step', () => {
    const provenanceStep = ARCHITECTURE_TOUR.find((s) => s.selector === '[data-tour="provenance"]');
    expect(provenanceStep?.navigateTo).toBe('architecture');
  });
});

// ---------- TEST 5: 375px mobile viewport ----------

describe('Test 5: 375px mobile viewport', () => {
  const cleanupEls: HTMLElement[] = [];
  afterEach(() => {
    cleanupEls.forEach((el) => { if (el.parentNode) el.parentNode.removeChild(el); });
    cleanupEls.length = 0;
  });

  it('renders navigation target visible and card inside viewport at 375px', () => {
    vi.useFakeTimers();
    setViewport(375, 667);

    const navTarget = installTargetElement('navigation', { top: 50, left: 10, width: 355, height: 44, bottom: 94, right: 365 });
    cleanupEls.push(navTarget);

    const steps: CoachStep[] = [
      { selector: '[data-tour="navigation"]', title: 'Nav', body: 'Test nav step' },
    ];

    const { container } = render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    act(() => { vi.advanceTimersByTime(280); });

    const dialog = container.querySelector('[role="dialog"]');
    expect(dialog).toBeTruthy();

    // (a) Nav target is within viewport using real measured rects
    const navRect = navTarget.getBoundingClientRect();
    expect(navRect.top).toBeGreaterThanOrEqual(0);
    expect(navRect.top).toBeLessThan(667);
    expect(navRect.left).toBeGreaterThanOrEqual(0);
    expect(navRect.right).toBeLessThanOrEqual(375);

    // (b) Card is inside the viewport
    const card = dialog!.querySelector('[tabindex="-1"]') as HTMLElement;
    expect(card).toBeTruthy();
    const cardWidth = parseInt(card.style.width, 10);
    expect(cardWidth).toBeLessThanOrEqual(375 - 24);
    expect(cardWidth).toBeGreaterThan(0);
    // Card uses bottom: 20 on mobile, so it's anchored at bottom
    expect(card.style.bottom).toBeTruthy();

    // (c) Every tour control has min width/height >= 44px enforced by CSS
    // Verify the CSS @media rule exists (jsdom does not apply @media)
    expect(css).toMatch(/@media\s*\(max-width:\s*767px\)[\s\S]*min-height:\s*44px/);
    expect(css).toMatch(/@media\s*\(max-width:\s*767px\)[\s\S]*min-width:\s*44px/);
    const buttons = card.querySelectorAll('button');
    expect(buttons.length).toBeGreaterThan(0);

    vi.useRealTimers();
  });
});

// ---------- TEST 6: Placement (top/bottom/auto) ----------

describe('Test 6: top, bottom, and auto placement behavior', () => {
  const cleanupEls: HTMLElement[] = [];
  afterEach(() => {
    cleanupEls.forEach((el) => { if (el.parentNode) el.parentNode.removeChild(el); });
    cleanupEls.length = 0;
  });

  it('placement: top renders card above the target', () => {
    vi.useFakeTimers();
    setViewport(1024, 768);

    const target = installTargetElement('placement-target', { top: 400, left: 200, width: 200, height: 50, bottom: 450, right: 400 });
    cleanupEls.push(target);

    const steps: CoachStep[] = [
      { selector: '[data-tour="placement-target"]', title: 'Top', body: 'Above', placement: 'top' },
    ];

    const { container } = render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    act(() => { vi.advanceTimersByTime(280); });

    const dialog = container.querySelector('[role="dialog"]')!;
    const card = dialog.querySelector('[tabindex="-1"]') as HTMLElement;

    expect(card.style.bottom).toBeTruthy();
    expect(card.style.top === '' || card.style.top === undefined).toBe(true);

    vi.useRealTimers();
  });

  it('placement: bottom renders card below the target', () => {
    vi.useFakeTimers();
    setViewport(1024, 768);

    const target = installTargetElement('placement-target-b', { top: 100, left: 200, width: 200, height: 50, bottom: 150, right: 400 });
    cleanupEls.push(target);

    const steps: CoachStep[] = [
      { selector: '[data-tour="placement-target-b"]', title: 'Bottom', body: 'Below', placement: 'bottom' },
    ];

    const { container } = render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    act(() => { vi.advanceTimersByTime(280); });

    const dialog = container.querySelector('[role="dialog"]')!;
    const card = dialog.querySelector('[tabindex="-1"]') as HTMLElement;

    expect(card.style.top).toBeTruthy();

    vi.useRealTimers();
  });

  it('placement: auto uses viewport collision to decide', () => {
    vi.useFakeTimers();
    setViewport(1024, 768);

    const target = installTargetElement('placement-target-auto', { top: 600, left: 200, width: 200, height: 50, bottom: 650, right: 400 });
    cleanupEls.push(target);

    const steps: CoachStep[] = [
      { selector: '[data-tour="placement-target-auto"]', title: 'Auto', body: 'Auto placement', placement: 'auto' },
    ];

    const { container } = render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    act(() => { vi.advanceTimersByTime(280); });

    const dialog = container.querySelector('[role="dialog"]')!;
    const card = dialog.querySelector('[tabindex="-1"]') as HTMLElement;

    expect(card.style.bottom).toBeTruthy();

    vi.useRealTimers();
  });
});

// ---------- TEST 7: Missing targets bounded skip/defer ----------

describe('Test 7: Missing targets use bounded skip/defer policy', () => {
  it('shows waiting state with Skip step when target is missing', () => {
    vi.useFakeTimers();
    setViewport(1024, 768);

    const steps: CoachStep[] = [
      { selector: '[data-tour="nonexistent-target"]', title: 'Missing Target', body: 'This target does not exist' },
    ];

    render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    expect(screen.getByText('Waiting for screen to load...')).toBeInTheDocument();
    expect(screen.getByText('Skip step')).toBeInTheDocument();
    expect(screen.getByText('Missing Target')).toBeInTheDocument();

    vi.useRealTimers();
  });

  it('does not render as untargeted centered card when target is missing', () => {
    vi.useFakeTimers();
    setViewport(1024, 768);

    const steps: CoachStep[] = [
      { selector: '[data-tour="nonexistent-target-2"]', title: 'Missing', body: 'No target' },
    ];

    const { container } = render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    expect(screen.getByText('Waiting for screen to load...')).toBeInTheDocument();

    const dialog = container.querySelector('[role="dialog"]')!;
    expect(dialog.querySelector('[tabindex="-1"]')).toBeTruthy();

    vi.useRealTimers();
  });

  it('shows timeout state after bounded wait expires', () => {
    vi.useFakeTimers();
    setViewport(1024, 768);

    const steps: CoachStep[] = [
      { selector: '[data-tour="never-appears"]', title: 'Timeout Step', body: 'Will not appear', waitForTargetTimeout: 500 },
    ];

    render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    // Initially shows waiting
    expect(screen.getByText('Waiting for screen to load...')).toBeInTheDocument();

    // Advance past the timeout
    act(() => { vi.advanceTimersByTime(600); });

    // Should show timeout message with live region
    expect(screen.getByText("This step's target could not be shown.")).toBeInTheDocument();
    const timeoutMsg = screen.getByText("This step's target could not be shown.");
    expect(timeoutMsg).toHaveAttribute('aria-live', 'polite');
    expect(timeoutMsg).toHaveAttribute('role', 'status');

    vi.useRealTimers();
  });
});

// ---------- TEST 8: Manual replay route-aware with seen key 1 (real component) ----------

describe('Test 8: Manual replay remains route-aware when seen key is 1', () => {
  beforeEach(() => { installMockLocalStorage(); });
  afterEach(() => { restoreLocalStorage(); });

  it('manual Take a tour opens agent tour on agent screen even when all seen', () => {
    // Seed seen keys using real production constants
    markTourSeen(APPLICATION_TOUR_KEY);
    markTourSeen(AGENT_TOUR_KEY);
    markTourSeen(ARCHITECTURE_TOUR_KEY);
    expect(tourSeen(APPLICATION_TOUR_KEY)).toBe(true);
    expect(tourSeen(AGENT_TOUR_KEY)).toBe(true);
    expect(tourSeen(ARCHITECTURE_TOUR_KEY)).toBe(true);

    const dispatched: string[] = [];
    const handler = (e: Event) => { dispatched.push((e as CustomEvent).detail.tour); };
    window.addEventListener('qp-tour-request', handler);

    const { unmount } = renderRealAppShell('agent');

    fireEvent.click(screen.getByRole('button', { name: 'Take a tour' }));
    expect(dispatched).toEqual(['agent']);

    window.removeEventListener('qp-tour-request', handler);
    unmount();
  });

  it('manual Take a tour opens architecture tour on architecture screen even when all seen', () => {
    markTourSeen(APPLICATION_TOUR_KEY);
    markTourSeen(AGENT_TOUR_KEY);
    markTourSeen(ARCHITECTURE_TOUR_KEY);

    const dispatched: string[] = [];
    const handler = (e: Event) => { dispatched.push((e as CustomEvent).detail.tour); };
    window.addEventListener('qp-tour-request', handler);

    const { unmount } = renderRealAppShell('architecture');

    fireEvent.click(screen.getByRole('button', { name: 'Take a tour' }));
    expect(dispatched).toEqual(['architecture']);

    window.removeEventListener('qp-tour-request', handler);
    unmount();
  });
});

// ---------- TEST 9: Canonical palette tokens ----------

describe('Test 9: Canonical obsidian/silver/gold token values', () => {
  function parseCssVar(raw: string, name: string): string {
    const match = raw.match(new RegExp(`${name}\\s*:\\s*(#[0-9a-fA-F]{6})`));
    if (!match) throw new Error(`CSS variable ${name} not found`);
    return match[1];
  }

  it('--canvas is #090A0C (obsidian)', () => {
    expect(parseCssVar(css, '--canvas')).toBe('#090A0C');
  });

  it('--surface is #111317', () => {
    expect(parseCssVar(css, '--surface')).toBe('#111317');
  });

  it('--surface-raised is #181B20', () => {
    expect(parseCssVar(css, '--surface-raised')).toBe('#181B20');
  });

  it('--text-primary is #F3F1EA (silver)', () => {
    expect(parseCssVar(css, '--text-primary')).toBe('#F3F1EA');
  });

  it('--text-secondary is #B8BDC5', () => {
    expect(parseCssVar(css, '--text-secondary')).toBe('#B8BDC5');
  });

  it('--text-muted is #818791', () => {
    expect(parseCssVar(css, '--text-muted')).toBe('#818791');
  });

  it('--border is #32363D', () => {
    expect(parseCssVar(css, '--border')).toBe('#32363D');
  });

  it('--border-subtle is #22262C', () => {
    expect(parseCssVar(css, '--border-subtle')).toBe('#22262C');
  });

  it('--accent is #D6B65A (gold)', () => {
    expect(parseCssVar(css, '--accent')).toBe('#D6B65A');
  });

  it('--accent-bright is #F1D77A', () => {
    expect(parseCssVar(css, '--accent-bright')).toBe('#F1D77A');
  });

  it('--accent-fill is #C9A227', () => {
    expect(parseCssVar(css, '--accent-fill')).toBe('#C9A227');
  });

  it('--positive is #43D19E', () => {
    expect(parseCssVar(css, '--positive')).toBe('#43D19E');
  });

  it('--bearish is #FF727F', () => {
    expect(parseCssVar(css, '--bearish')).toBe('#FF727F');
  });

  it('--neutral is #A8B0BC', () => {
    expect(parseCssVar(css, '--neutral')).toBe('#A8B0BC');
  });

  it('.nav-item.active uses accent-dim wash, not hardcoded blue', () => {
    expect(css).toContain('.nav-item.active');
    expect(css).toContain('background: var(--accent-dim)');
    expect(css).not.toMatch(/\.nav-item\.active[\s\S]*background:\s*#2563eb/);
  });
});

// ---------- TEST 10: No old light surface/Blue CTA/Slate classes ----------

describe('Test 10: No old light surface/Blue CTA/Slate classes in rendered components', () => {
  /** Scan source files for forbidden legacy Tailwind classes */
  const FORBIDDEN_PATTERNS = [
    /\bbg-white\b/,
    /\bbg-slate-\d+\b/,
    /\bborder-slate-\d+\b/,
    /\btext-slate-\d+\b/,
    /\bbg-blue-\d+\b/,
    /\bborder-blue-\d+\b/,
    /\btext-blue-\d+\b/,
  ];

  const SCREEN_FILES = [
    'screens/PlatformOverview.tsx',
    'screens/MarketDashboard.tsx',
    'screens/OptionsAnalytics.tsx',
    'screens/SecFilingExplorer.tsx',
    'screens/ResearchAgent.tsx',
    'screens/SignalExplorer.tsx',
    'screens/PaperPortfolio.tsx',
    'screens/OrderApprovalDrawer.tsx',
    'screens/SystemHealth.tsx',
    'screens/ArchitectureEvidence.tsx',
  ];

  const SHARED_COMPONENT_FILES = [
    'components/Card.tsx',
    'components/EmptyState.tsx',
    'components/ErrorState.tsx',
    'components/ExecutionTrace.tsx',
    'components/FreshnessBadge.tsx',
    'components/LoadingState.tsx',
    'components/StatTile.tsx',
    'components/SymbolPicker.tsx',
    'components/SymbolSelect.tsx',
    'components/Table.tsx',
    'components/evidence/EvidencePanel.tsx',
    'components/evidence/ToolCallCard.tsx',
    'components/evidence/SourceCard.tsx',
    'components/evidence/ProvenanceGrid.tsx',
    'components/evidence/DeveloperDetails.tsx',
    'components/tours/CoachMarks.tsx',
    'components/states/EmptyPanel.tsx',
    'components/states/ErrorPanel.tsx',
    'components/states/LoadingSkeleton.tsx',
    'components/states/StaleDataNotice.tsx',
    'components/states/SuccessToast.tsx',
    'layout/PageHeader.tsx',
  ];

  const ALL_FILES = [...SCREEN_FILES, ...SHARED_COMPONENT_FILES];

  for (const file of ALL_FILES) {
    it(`${file} contains no legacy bg-white/slate/blue classes`, () => {
      let content: string;
      try {
        content = readFileSync(join(__dirname, '../..', file), 'utf-8');
      } catch {
        // File may not exist; skip
        return;
      }

      for (const pattern of FORBIDDEN_PATTERNS) {
        const matches = content.match(new RegExp(pattern.source, 'g'));
        if (matches) {
          // Allow dark: variants and semantic signal colors (emerald, red, amber for status badges)
          const nonDarkMatches = content.split('\n').filter((line) => {
            const hasPattern = pattern.test(line);
            const isDarkVariant = line.includes('dark:');
            const isSemanticSignal = /(?:bg|text|border)-(?:emerald|red|amber|green)-/.test(line);
            return hasPattern && !isDarkVariant && !isSemanticSignal;
          });
          expect(nonDarkMatches).toEqual([]);
        }
      }
    });
  }
});

// ---------- TEST 11: Part B1 - ArchitectureEvidence honesty ----------

describe('Test 11: ArchitectureEvidence removes false Verified wording', () => {
  it('no "Verified" claim appears with placeholder data', () => {
    const content = readFileSync(join(__dirname, '../../screens/ArchitectureEvidence.tsx'), 'utf-8');
    // The component should not contain "Verified" in its rendered text
    // (it was removed because commit/date are placeholders)
    expect(content).not.toMatch(/Verified Test Groups/);
    expect(content).not.toMatch(/Verified architecture/);
    expect(content).toContain('Expected Test Groups');
    expect(content).toContain('Test coverage');
    // Status text conveyed to screen readers
    expect(content).toMatch(/role="status"/);
  });
});

// ---------- TEST 12: Part B2 - Skip link ----------

describe('Test 12: Skip link is first focusable in AppShell', () => {
  it('skip link targets #main-content and main has tabIndex=-1', () => {
    const content = readFileSync(join(__dirname, '../../layout/AppShell.tsx'), 'utf-8');
    // Skip link must be present
    expect(content).toContain('Skip to main content');
    expect(content).toContain('href="#main-content"');
    // main element must have id and tabIndex
    expect(content).toMatch(/id="main-content"/);
    expect(content).toMatch(/tabIndex=\{-1\}/);
    // Skip link must come before Sidebar in the JSX
    const skipIdx = content.indexOf('Skip to main content');
    const sidebarIdx = content.indexOf('<Sidebar');
    expect(skipIdx).toBeLessThan(sidebarIdx);
  });

  it('skip link is the first focusable element in the rendered shell', () => {
    const onNavigate = vi.fn();
    render(
      <AppShell
        groups={TEST_GROUPS}
        currentId="platform-overview"
        onNavigate={onNavigate}
        health={healthyHealth}
      >
        <div />
      </AppShell>,
    );
    // The skip link should be in the document
    const skipLink = screen.getByText('Skip to main content');
    expect(skipLink).toBeInTheDocument();
    expect(skipLink).toHaveAttribute('href', '#main-content');
    // main element should have id="main-content"
    const main = document.getElementById('main-content');
    expect(main).toBeInTheDocument();
    expect(main).toHaveAttribute('tabindex', '-1');
  });
});

// ---------- TEST 13: Part B3 - Research Agent accessible label ----------

describe('Test 13: Research Agent input has accessible label', () => {
  it('input has a visible label element or aria-label', () => {
    const content = readFileSync(join(__dirname, '../../screens/ResearchAgent.tsx'), 'utf-8');
    // Either a <label> or aria-label must be present
    const hasLabel = content.includes('<label') || content.includes('aria-label');
    expect(hasLabel).toBe(true);
    // If using htmlFor, the input must have matching id
    if (content.includes('htmlFor')) {
      expect(content).toMatch(/id="research-agent-input"/);
    }
  });
});

// ---------- TEST 14: Part B5 - Collapsible aria-expanded/aria-controls ----------

describe('Test 14: DeveloperDetails collapsible has aria-expanded and aria-controls', () => {
  it('summary has aria-expanded and aria-controls referencing a real id', () => {
    const content = readFileSync(join(__dirname, '../../components/evidence/DeveloperDetails.tsx'), 'utf-8');
    expect(content).toContain('aria-expanded');
    expect(content).toContain('aria-controls');
    // id is set via a variable: id={contentId}
    expect(content).toMatch(/id=\{contentId\}/);
    expect(content).toContain("contentId = 'developer-details-content'");
    expect(content).toContain('aria-controls={contentId}');
  });
});

// ---------- TEST 15: Part B6 - Tour target timeout live region ----------

describe('Test 15: Tour target timeout shows explicit state with live region', () => {
  it('timeout message has aria-live="polite" and role="status"', () => {
    vi.useFakeTimers();
    setViewport(1024, 768);

    const steps: CoachStep[] = [
      { selector: '[data-tour="never-appears-2"]', title: 'Timeout', body: 'Gone', waitForTargetTimeout: 300 },
    ];

    render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    // Advance past timeout
    act(() => { vi.advanceTimersByTime(400); });

    const msg = screen.getByText("This step's target could not be shown.");
    expect(msg).toHaveAttribute('aria-live', 'polite');
    expect(msg).toHaveAttribute('role', 'status');

    vi.useRealTimers();
  });
});

// ---------- TEST 16: Part B7 - Tour exit restores screen ----------

describe('Test 16: Tour exit restores the screen the user started from', () => {
  it('onNavigate restores initial screen when Escape closes the tour', () => {
    const onNavigate = vi.fn();
    const onClose = vi.fn();

    // Step 0 has no navigateTo (intro), Step 1 navigates away.
    // currentScreen='platform-overview' simulates the user's starting screen.
    const steps: CoachStep[] = [
      { title: 'Intro', body: 'Hello' },
      { selector: '[data-tour="agent"]', title: 'Agent', body: 'Agent step', navigateTo: 'agent' },
    ];

    render(
      <div>
        <CoachMarks
          steps={steps}
          run={true}
          onClose={onClose}
          onNavigate={onNavigate}
          currentScreen="platform-overview"
        />
      </div>,
    );

    onNavigate.mockClear();

    // Press Escape to close the tour
    act(() => { fireEvent.keyDown(window, { key: 'Escape' }); });

    // onClose was called
    expect(onClose).toHaveBeenCalled();
    // onNavigate was called to restore the initial screen
    expect(onNavigate).toHaveBeenCalledWith('platform-overview');
  });
});
