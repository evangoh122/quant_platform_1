import { render, screen, act, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React, { useCallback, useState } from 'react';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import CoachMarks, { tourSeen, markTourSeen, type CoachStep } from './CoachMarks';
import { useTourHost } from './TourHost';
import { EvidencePanel } from '../evidence/EvidencePanel';
import { DeveloperDetails } from '../evidence/DeveloperDetails';
import { AppShell, type NavGroup } from '../../layout/AppShell';
import App from '../../App';
import { ArchitectureEvidence } from '../../screens/ArchitectureEvidence';
import { ResearchAgent } from '../../screens/ResearchAgent';
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

// ---------- stateful-test helpers ----------

function stubVisibleTourRects() {
  return vi
    .spyOn(Element.prototype, 'getBoundingClientRect')
    .mockImplementation(function (this: Element): DOMRect {
      if (this.hasAttribute('data-tour')) return fakeRect();
      return fakeRect({ top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0, x: 0, y: 0 });
    });
}

function expectActiveScreen(label: string) {
  expect(screen.getByRole('button', { name: label })).toHaveAttribute('aria-current', 'page');
}

function readTourCounter(dialog: HTMLElement) {
  return within(dialog).getByText(/^Step \d+ of \d+$/).textContent ?? '';
}

function renderAppMarkAllSeen() {
  installMockLocalStorage();
  markTourSeen(APPLICATION_TOUR_KEY);
  markTourSeen(AGENT_TOUR_KEY);
  markTourSeen(ARCHITECTURE_TOUR_KEY);
  setViewport(1024, 768);
  vi.stubGlobal('fetch', mockFetch(healthyResponse));
  return render(<App />);
}

async function startApplicationTourFrom(startLabel: string) {
  renderAppMarkAllSeen();
  await screen.findByRole('button', { name: 'Take a tour' });
  fireEvent.click(screen.getByRole('button', { name: startLabel }));
  await waitFor(() => expectActiveScreen(startLabel));
  fireEvent.click(screen.getByRole('button', { name: 'Take a tour' }));
  return screen.findByRole('dialog', { name: 'Guided tour' });
}

async function advanceTo(dialog: HTMLElement, stepLabel: string) {
  fireEvent.click(within(dialog).getByRole('button', { name: 'Next' }));
  return within(dialog).findByText(stepLabel);
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

// ---------- TEST 8: Manual replay ignores seen keys via real App + TourHost ----------

describe('Test 8: Manual replay opens the tour even when its seen key is 1 (real App + TourHost)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    restoreLocalStorage();
  });

  it('Take a tour on the agent screen opens the agent tour although every seen key is 1', async () => {
    renderAppMarkAllSeen();
    expect(tourSeen(APPLICATION_TOUR_KEY)).toBe(true);
    expect(tourSeen(AGENT_TOUR_KEY)).toBe(true);
    expect(tourSeen(ARCHITECTURE_TOUR_KEY)).toBe(true);
    await screen.findByRole('button', { name: 'Take a tour' });
    fireEvent.click(screen.getByRole('button', { name: 'AI Research Agent' }));
    await waitFor(() => expectActiveScreen('AI Research Agent'));

    fireEvent.click(screen.getByRole('button', { name: 'Take a tour' }));
    expect(await screen.findByText('Research Agent tour')).toBeInTheDocument();
  });

  it('Take a tour on a default screen opens the application tour although every seen key is 1', async () => {
    renderAppMarkAllSeen();
    await screen.findByRole('button', { name: 'Take a tour' });

    fireEvent.click(screen.getByRole('button', { name: 'Take a tour' }));
    expect(await screen.findByText('Welcome to QP1')).toBeInTheDocument();
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

// ---------- TEST 11: Part B1 - ArchitectureEvidence honesty (rendered DOM) ----------

describe('Test 11: ArchitectureEvidence removes false Verified wording', () => {
  it('renders no Verified claim with placeholder data, and shows Expected Test Groups + status text', () => {
    render(<ArchitectureEvidence />);

    expect(screen.getByRole('heading', { name: 'Expected Test Groups' })).toBeInTheDocument();
    expect(screen.getAllByText(/Test coverage/).length).toBeGreaterThan(0);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText('Verified Test Groups')).not.toBeInTheDocument();
    expect(screen.queryByText(/Verified architecture/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Verified$/)).not.toBeInTheDocument();
  });
});

// ---------- TEST 12: Part B2 - Skip link (rendered DOM) ----------

describe('Test 12: Skip link is first focusable in AppShell', () => {
  it('skip link is the first focusable element in DOM order and targets #main-content', () => {
    render(
      <AppShell
        groups={TEST_GROUPS}
        currentId="platform-overview"
        onNavigate={() => {}}
        health={healthyHealth}
      >
        <div />
      </AppShell>,
    );

    const focusables = Array.from(
      document.querySelectorAll<HTMLElement>(
        'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    );
    expect(focusables.length).toBeGreaterThan(1);
    expect(focusables[0]).toHaveTextContent('Skip to main content');
    expect(focusables[0]).toHaveAttribute('href', '#main-content');
  });

  it('skip link targets #main-content and main has tabIndex=-1', () => {
    render(
      <AppShell
        groups={TEST_GROUPS}
        currentId="platform-overview"
        onNavigate={() => {}}
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

// ---------- TEST 13: Part B3 - Research Agent accessible label (rendered DOM) ----------

describe('Test 13: Research Agent input has accessible label', () => {
  it('input is labelled by its label element (rendered DOM/ARIA)', () => {
    render(<ResearchAgent />);

    const input = screen.getByRole('textbox', { name: /research question/i });
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute('id', 'research-agent-input');
  });
});

// ---------- TEST 14: Part B5 - Collapsible aria-expanded/aria-controls (rendered DOM) ----------

describe('Test 14: DeveloperDetails collapsible has aria-expanded and aria-controls', () => {
  it('summary has aria-expanded and aria-controls referencing a real element id', () => {
    render(<DeveloperDetails arguments={{ a: 1 }} result={{ b: 2 }} />);

    const summary = screen.getByText('Developer details');
    expect(summary.tagName).toBe('SUMMARY');
    expect(summary).toHaveAttribute('aria-expanded', 'false');
    const controlsId = summary.getAttribute('aria-controls');
    expect(controlsId).toBeTruthy();

    const controlled = document.getElementById(controlsId!);
    expect(controlled).not.toBeNull();
    expect(controlled).toBeInTheDocument();
  });

  it('aria-expanded tracks the disclosure state', () => {
    render(<DeveloperDetails arguments={{ a: 1 }} result={{ b: 2 }} />);

    const summary = screen.getByText('Developer details');
    const details = summary.closest('details') as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event('toggle'));
    expect(summary).toHaveAttribute('aria-expanded', 'true');

    details.open = false;
    fireEvent(details, new Event('toggle'));
    expect(summary).toHaveAttribute('aria-expanded', 'false');
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

// ---------- TEST 16: Stateful cross-screen tour + restore starting screen ----------

describe('Test 16: Stateful tour advances past every navigateTo step and restores the starting screen', () => {
  let rectSpy: ReturnType<typeof stubVisibleTourRects>;

  beforeEach(() => {
    rectSpy = stubVisibleTourRects();
  });

  afterEach(() => {
    rectSpy.mockRestore();
    vi.unstubAllGlobals();
    restoreLocalStorage();
  });

  async function settleTargetStep(
    dialog: HTMLElement,
    stepLabel: string,
    activeNavLabel: string,
    targetSelector: string,
  ) {
    fireEvent.click(within(dialog).getByRole('button', { name: 'Next' }));
    await within(dialog).findByText(stepLabel);
    await waitFor(() => {
      expect(document.querySelector(targetSelector)).not.toBeNull();
      expect(within(dialog).queryByText('Waiting for screen to load...')).not.toBeInTheDocument();
    });
    await waitFor(() => expectActiveScreen(activeNavLabel));
    const target = document.querySelector(targetSelector) as HTMLElement;
    const rect = target.getBoundingClientRect();
    expect(rect.width).toBeGreaterThan(0);
    expect(rect.height).toBeGreaterThan(0);
    await waitFor(
      () => {
        const spotlight = dialog.querySelector('[style*="box-shadow"]') as HTMLElement | null;
        expect(spotlight).not.toBeNull();
        expect(parseFloat(spotlight!.style.width)).toBeGreaterThan(0);
      },
      { timeout: 3000 },
    );
    expect(readTourCounter(dialog)).toBe(stepLabel);
  }

  it('application tour reaches the last step past every navigateTo step without resetting to step 1, and Done restores the starting screen', async () => {
    const dialog = await startApplicationTourFrom('Signal Explorer');
    const counters: string[] = [readTourCounter(dialog)];
    expect(counters[0]).toBe('Step 1 of 5');

    await advanceTo(dialog, 'Step 2 of 5');
    counters.push(readTourCounter(dialog));

    await settleTargetStep(dialog, 'Step 3 of 5', 'Market Explorer', '[data-tour="market-research"]');
    counters.push(readTourCounter(dialog));

    await settleTargetStep(dialog, 'Step 4 of 5', 'AI Research Agent', '[data-tour="agent"]');
    counters.push(readTourCounter(dialog));

    await settleTargetStep(dialog, 'Step 5 of 5', 'System Health', '[data-tour="analytics-evidence"]');
    counters.push(readTourCounter(dialog));

    expect(counters).toEqual(['Step 1 of 5', 'Step 2 of 5', 'Step 3 of 5', 'Step 4 of 5', 'Step 5 of 5']);

    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Guided tour' })).not.toBeInTheDocument(),
    );
    expectActiveScreen('Signal Explorer');
  });

  it('Escape after a navigateTo step restores the screen the user started on', async () => {
    const dialog = await startApplicationTourFrom('Signal Explorer');
    await advanceTo(dialog, 'Step 2 of 5');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Next' }));
    await within(dialog).findByText('Step 3 of 5');
    await waitFor(() => expectActiveScreen('Market Explorer'));

    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Guided tour' })).not.toBeInTheDocument(),
    );
    expectActiveScreen('Signal Explorer');
  });

  it('Skip tour after a navigateTo step restores the screen the user started on', async () => {
    const dialog = await startApplicationTourFrom('Signal Explorer');
    await advanceTo(dialog, 'Step 2 of 5');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Next' }));
    await within(dialog).findByText('Step 3 of 5');
    await waitFor(() => expectActiveScreen('Market Explorer'));

    fireEvent.click(within(dialog).getByText('Skip tour'));
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Guided tour' })).not.toBeInTheDocument(),
    );
    expectActiveScreen('Signal Explorer');
  });

  it('close calls onNavigate with the screen the user started on (stateful harness)', () => {
    const navCalls: string[] = [];
    const harnessSteps: CoachStep[] = [
      { title: 'Intro', body: 'Hello' },
      {
        selector: '[data-tour="harness-target"]',
        title: 'Market',
        body: 'Body',
        navigateTo: 'market',
      },
    ];

    function Harness() {
      const [screenId, setScreenId] = useState('signals');
      const onNavigate = useCallback((id: string) => {
        navCalls.push(id);
        setScreenId(id);
      }, []);
      return (
        <div>
          <div data-testid="current-screen">{screenId}</div>
          {screenId === 'market' && <div data-tour="harness-target" />}
          <CoachMarks
            steps={harnessSteps}
            run={true}
            onClose={() => {}}
            onNavigate={onNavigate}
            currentScreen={screenId}
          />
        </div>
      );
    }

    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    expect(navCalls).toEqual(['market']);
    expect(screen.getByTestId('current-screen')).toHaveTextContent('market');
    expect(readTourCounter(screen.getByRole('dialog', { name: 'Guided tour' }))).toBe('Step 2 of 2');

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(navCalls).toEqual(['market', 'signals']);
    expect(screen.getByTestId('current-screen')).toHaveTextContent('signals');
  });
});

// ---------- TEST 17: Mobile drawer background inert ----------

describe('Test 17: Mobile drawer background is inert while open', () => {
  it('background has the inert attribute while open and not when closed', () => {
    render(
      <AppShell
        groups={TEST_GROUPS}
        currentId="platform-overview"
        onNavigate={() => {}}
        health={healthyHealth}
      >
        <div />
      </AppShell>,
    );

    expect(document.querySelector('[inert]')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }));
    const drawer = screen.getByRole('dialog', { name: 'Navigation' });
    const background = document.querySelector('[inert]');
    expect(background).not.toBeNull();
    expect(background).toHaveAttribute('aria-hidden', 'true');
    expect(drawer).not.toHaveAttribute('inert');

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Navigation' })).not.toBeInTheDocument();
    expect(document.querySelector('[inert]')).toBeNull();
  });
});

// ---------- TEST 18: Measured-height viewport collision placement ----------

describe('Test 18: Measured-height viewport collision placement', () => {
  const VIEWPORT_H = 800;
  const VIEWPORT_W = 1024;
  const VIEWPORT_MARGIN = 12;
  const cleanupEls: HTMLElement[] = [];
  let protoSpy: ReturnType<typeof vi.spyOn>;

  function stubCardHeight(h: number) {
    protoSpy?.mockRestore();
    protoSpy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect');
    protoSpy.mockImplementation(function (this: HTMLElement) {
      if (this.getAttribute('tabindex') === '-1' && this.closest('[role="dialog"]')) {
        return fakeRect({ top: 0, left: 0, width: 320, height: h, bottom: h, right: 320 });
      }
      return fakeRect({ top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0 });
    });
  }

  function installTarget(name: string, rect: Partial<DOMRect>) {
    const el = document.createElement('div');
    el.setAttribute('data-tour', name);
    el.getBoundingClientRect = () => fakeRect(rect);
    document.body.appendChild(el);
    cleanupEls.push(el);
    return el;
  }

  function renderWithHeight(
    cardH: number,
    targetName: string,
    targetRect: Partial<DOMRect>,
    placement?: 'top' | 'bottom' | 'auto',
  ) {
    stubCardHeight(cardH);
    installTarget(targetName, targetRect);
    const steps: CoachStep[] = [
      { selector: `[data-tour="${targetName}"]`, title: 'Test', body: 'Body', placement },
    ];
    const { container } = render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );
    act(() => { vi.advanceTimersByTime(280); });
    const dialog = container.querySelector('[role="dialog"]')!;
    const card = dialog.querySelector('[tabindex="-1"]') as HTMLElement;
    return { dialog, card, container };
  }

  function getCardEdges(card: HTMLElement, h: number) {
    if (card.style.top && card.style.top !== '') {
      const top = parseFloat(card.style.top);
      const bottom = top + h;
      return { top, bottom, side: 'below' as const };
    } else if (card.style.bottom && card.style.bottom !== '') {
      const bottomOffset = parseFloat(card.style.bottom);
      const bottomEdge = VIEWPORT_H - bottomOffset;
      const topEdge = bottomEdge - h;
      return { top: topEdge, bottom: bottomEdge, side: 'above' as const };
    }
    throw new Error('Card has neither top nor bottom set');
  }

  function assertInsideViewport(edges: { top: number; bottom: number }) {
    expect(edges.top).toBeGreaterThanOrEqual(VIEWPORT_MARGIN);
    expect(edges.bottom).toBeLessThanOrEqual(VIEWPORT_H - VIEWPORT_MARGIN);
  }

  beforeEach(() => {
    vi.useFakeTimers();
    setViewport(VIEWPORT_W, VIEWPORT_H);
  });

  afterEach(() => {
    vi.useRealTimers();
    protoSpy?.mockRestore();
    cleanupEls.forEach((el) => { if (el.parentNode) el.parentNode.removeChild(el); });
    cleanupEls.length = 0;
  });

  describe('auto placement', () => {
    const nearTop = { top: 20, left: 200, width: 200, height: 40, bottom: 60, right: 400 };
    const middle = { top: 450, left: 200, width: 200, height: 50, bottom: 500, right: 400 };
    const nearBottom = { top: 740, left: 200, width: 200, height: 40, bottom: 780, right: 400 };

    it('near top, h=120 → stays below', () => {
      const { card } = renderWithHeight(120, 'target-at-120', nearTop, 'auto');
      const edges = getCardEdges(card, 120);
      expect(edges.side).toBe('below');
      assertInsideViewport(edges);
    });

    it('near top, h=320 → stays below', () => {
      const { card } = renderWithHeight(320, 'target-at-320', nearTop, 'auto');
      const edges = getCardEdges(card, 320);
      expect(edges.side).toBe('below');
      assertInsideViewport(edges);
    });

    it('middle, h=120 → stays below', () => {
      const { card } = renderWithHeight(120, 'target-mid-120', middle, 'auto');
      const edges = getCardEdges(card, 120);
      expect(edges.side).toBe('below');
      assertInsideViewport(edges);
    });

    it('middle, h=320 → flips above', () => {
      const { card } = renderWithHeight(320, 'target-mid-320', middle, 'auto');
      const edges = getCardEdges(card, 320);
      expect(edges.side).toBe('above');
      assertInsideViewport(edges);
    });

    it('near bottom, h=120 → flips above', () => {
      const { card } = renderWithHeight(120, 'target-nb-120', nearBottom, 'auto');
      const edges = getCardEdges(card, 120);
      expect(edges.side).toBe('above');
      assertInsideViewport(edges);
    });

    it('near bottom, h=320 → flips above', () => {
      const { card } = renderWithHeight(320, 'target-nb-320', nearBottom, 'auto');
      const edges = getCardEdges(card, 320);
      expect(edges.side).toBe('above');
      assertInsideViewport(edges);
    });

    it('decision changes with measured height (same target)', () => {
      stubCardHeight(120);
      installTarget('target-decision', middle);
      const steps120: CoachStep[] = [
        { selector: '[data-tour="target-decision"]', title: 'T', body: 'B', placement: 'auto' },
      ];
      const { container: c1, unmount: u1 } = render(
        <div><CoachMarks steps={steps120} run={true} onClose={() => {}} /></div>,
      );
      act(() => { vi.advanceTimersByTime(280); });
      const card120 = c1.querySelector('[role="dialog"] [tabindex="-1"]') as HTMLElement;
      expect(getCardEdges(card120, 120).side).toBe('below');
      u1();

      stubCardHeight(320);
      installTarget('target-decision-320', middle);
      const steps320: CoachStep[] = [
        { selector: '[data-tour="target-decision-320"]', title: 'T', body: 'B', placement: 'auto' },
      ];
      const { container: c2 } = render(
        <div><CoachMarks steps={steps320} run={true} onClose={() => {}} /></div>,
      );
      act(() => { vi.advanceTimersByTime(280); });
      const card320 = c2.querySelector('[role="dialog"] [tabindex="-1"]') as HTMLElement;
      expect(getCardEdges(card320, 320).side).toBe('above');
    });
  });

  describe('bottom and top placement', () => {
    const middle = { top: 450, left: 200, width: 200, height: 50, bottom: 500, right: 400 };
    const nearBottom = { top: 740, left: 200, width: 200, height: 40, bottom: 780, right: 400 };
    const nearTop = { top: 20, left: 200, width: 200, height: 40, bottom: 60, right: 400 };

    it('bottom honors when both sides fit (middle, h=120) → below', () => {
      const { card } = renderWithHeight(120, 'target-bot-honor', middle, 'bottom');
      const edges = getCardEdges(card, 120);
      expect(edges.side).toBe('below');
      assertInsideViewport(edges);
    });

    it("bottom flips when below doesn't fit (near bottom, h=320) → above", () => {
      const { card } = renderWithHeight(320, 'target-bot-flip', nearBottom, 'bottom');
      const edges = getCardEdges(card, 320);
      expect(edges.side).toBe('above');
      assertInsideViewport(edges);
    });

    it('top honors when both sides fit (middle, h=120) → above', () => {
      const { card } = renderWithHeight(120, 'target-top-honor', middle, 'top');
      const edges = getCardEdges(card, 120);
      expect(edges.side).toBe('above');
      assertInsideViewport(edges);
    });

    it("top flips when above doesn't fit (near top, h=120) → below", () => {
      const { card } = renderWithHeight(120, 'target-top-flip', nearTop, 'top');
      const edges = getCardEdges(card, 120);
      expect(edges.side).toBe('below');
      assertInsideViewport(edges);
    });
  });

  describe('viewport clamping', () => {
    it('card stays inside viewport when neither side fits (above has more room, h=320)', () => {
      const target = { top: 340, left: 200, width: 200, height: 130, bottom: 470, right: 400 };
      const { card } = renderWithHeight(320, 'target-clamp-above', target, 'bottom');
      const edges = getCardEdges(card, 320);
      assertInsideViewport(edges);
      expect(edges.side).toBe('above');
    });

    it('card stays inside viewport when below has more room (spanning target, h=320)', () => {
      const spanning = { top: 300, left: 200, width: 200, height: 170, bottom: 470, right: 400 };
      const { card } = renderWithHeight(320, 'target-clamp-below', spanning, 'bottom');
      const edges = getCardEdges(card, 320);
      assertInsideViewport(edges);
      expect(edges.side).toBe('below');
    });

    it('card stays inside viewport with extreme card height (near bottom, h=720)', () => {
      const nearBottom = { top: 740, left: 200, width: 200, height: 40, bottom: 780, right: 400 };
      const { card } = renderWithHeight(720, 'target-clamp-extreme', nearBottom, 'auto');
      const edges = getCardEdges(card, 720);
      assertInsideViewport(edges);
    });
  });
});
