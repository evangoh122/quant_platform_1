import { useState } from 'react';
import { render, screen, act, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import CoachMarks, { type CoachStep } from './CoachMarks';
import { AppShell, type NavGroup } from '../../layout/AppShell';
import App from '../../App';
import {
  APPLICATION_TOUR_KEY,
  AGENT_TOUR_KEY,
  ARCHITECTURE_TOUR_KEY,
} from './tourSteps';
import { markTourSeen } from './CoachMarks';

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

function renderAppMarkAllSeen() {
  installMockLocalStorage();
  markTourSeen(APPLICATION_TOUR_KEY);
  markTourSeen(AGENT_TOUR_KEY);
  markTourSeen(ARCHITECTURE_TOUR_KEY);
  setViewport(1024, 768);
  vi.stubGlobal('fetch', mockFetch(healthyResponse));
  return render(<App />);
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
      { id: 'signals', label: 'Signal Explorer' },
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

// =====================================================================
// TEST 1: Fix 1 — Reset index on close prevents stale navigateTo on replay
// =====================================================================

describe('r12 Fix 1: Reset index on close prevents stale navigateTo on replay', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    restoreLocalStorage();
  });

  it('completing the application tour and restarting from Signal Explorer keeps Signal Explorer active on step 1', async () => {
    const rectSpy = stubVisibleTourRects();

    renderAppMarkAllSeen();
    await screen.findByRole('button', { name: 'Take a tour' });

    // Start the application tour from Signal Explorer
    fireEvent.click(screen.getByRole('button', { name: 'Signal Explorer' }));
    await waitFor(() => expectActiveScreen('Signal Explorer'));
    fireEvent.click(screen.getByRole('button', { name: 'Take a tour' }));

    const dialog1 = await screen.findByRole('dialog', { name: 'Guided tour' });
    expect(within(dialog1).getByText('Step 1 of 5')).toBeInTheDocument();

    // Advance through all steps to Done
    fireEvent.click(within(dialog1).getByRole('button', { name: 'Next' }));
    await within(dialog1).findByText('Step 2 of 5');

    fireEvent.click(within(dialog1).getByRole('button', { name: 'Next' }));
    await within(dialog1).findByText('Step 3 of 5');
    await waitFor(() => expectActiveScreen('Market Explorer'));

    fireEvent.click(within(dialog1).getByRole('button', { name: 'Next' }));
    await within(dialog1).findByText('Step 4 of 5');
    await waitFor(() => expectActiveScreen('AI Research Agent'));

    fireEvent.click(within(dialog1).getByRole('button', { name: 'Next' }));
    await within(dialog1).findByText('Step 5 of 5');
    await waitFor(() => expectActiveScreen('System Health'));

    // Click Done to close the tour
    fireEvent.click(within(dialog1).getByRole('button', { name: 'Done' }));
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Guided tour' })).not.toBeInTheDocument(),
    );

    // Navigate to Signal Explorer and restart the tour
    fireEvent.click(screen.getByRole('button', { name: 'Signal Explorer' }));
    await waitFor(() => expectActiveScreen('Signal Explorer'));

    fireEvent.click(screen.getByRole('button', { name: 'Take a tour' }));
    const dialog2 = await screen.findByRole('dialog', { name: 'Guided tour' });

    // Step 1 must be showing; Signal Explorer must still be active
    expect(within(dialog2).getByText('Step 1 of 5')).toBeInTheDocument();
    expectActiveScreen('Signal Explorer');

    // No stray navigation announcement from previous tour on step 1
    expect(screen.queryByText(/Navigated to System Health/)).not.toBeInTheDocument();

    rectSpy.mockRestore();
  });
});

// =====================================================================
// TEST 2: Fix 2 — Deferred measure timer is cleared on cleanup
// =====================================================================

describe('r12 Fix 2: Deferred measure timer is cleared on cleanup', () => {
  const cleanupEls: HTMLElement[] = [];

  afterEach(() => {
    cleanupEls.forEach((el) => { if (el.parentNode) el.parentNode.removeChild(el); });
    cleanupEls.length = 0;
  });

  it('closing the tour within 280ms of target resolving does not leave stale rect', async () => {
    setViewport(1024, 768);

    function Harness() {
      const [run, setRun] = useState(true);
      return (
        <div>
          <CoachMarks
            steps={[
              { selector: '[data-tour="late-target"]', title: 'Late Step', body: 'Appears later', waitForTargetTimeout: 5000 },
            ]}
            run={run}
            onClose={() => setRun(false)}
          />
        </div>
      );
    }

    render(<Harness />);

    // Should be in waiting state
    expect(screen.getByText('Waiting for screen to load...')).toBeInTheDocument();

    // Now add the target element so MutationObserver fires
    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'late-target');
    targetEl.getBoundingClientRect = () => fakeRect({ left: 200, top: 200, width: 100, height: 50 });
    document.body.appendChild(targetEl);
    cleanupEls.push(targetEl);

    // Wait for the target to resolve (waiting text disappears)
    await waitFor(() => {
      expect(screen.queryByText('Waiting for screen to load...')).not.toBeInTheDocument();
    });

    // Close the tour immediately (within the 280ms deferred measure window)
    fireEvent.keyDown(window, { key: 'Escape' });

    // The dialog should be gone (run=false)
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('advancing to next step within 280ms of target resolving does not measure stale element', () => {
    vi.useFakeTimers();
    setViewport(1024, 768);

    const target1 = document.createElement('div');
    target1.setAttribute('data-tour', 'r12-t1');
    target1.getBoundingClientRect = () => fakeRect({ left: 100, top: 100, width: 100, height: 50 });
    document.body.appendChild(target1);
    cleanupEls.push(target1);

    const steps: CoachStep[] = [
      { selector: '[data-tour="r12-t1"]', title: 'Step A', body: 'A' },
      { title: 'Step B', body: 'B' },
    ];

    const { container } = render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );

    // Let initial measure complete
    act(() => { vi.advanceTimersByTime(280); });

    const dialog = container.querySelector('[role="dialog"]')! as HTMLElement;
    expect(within(dialog).getByText('Step A')).toBeInTheDocument();

    // Move to step 2 immediately
    fireEvent.click(within(dialog).getByRole('button', { name: 'Next' }));
    expect(within(dialog).getByText('Step B')).toBeInTheDocument();

    // Step 2 has no selector, so rect should be null (centered card)
    // If the deferred timer from step1 wasn't cleared, it would set rect to step1's element
    act(() => { vi.advanceTimersByTime(500); });

    // The card should still be showing Step B (not a stale spotlight from step A)
    expect(within(dialog).getByText('Step B')).toBeInTheDocument();

    vi.useRealTimers();
  });
});

// =====================================================================
// TEST 3: Fix 3 — Focus management across waiting/normal card swap
// =====================================================================

describe('r12 Fix 3: Focus management across waiting/normal card swap', () => {
  const cleanupEls: HTMLElement[] = [];

  afterEach(() => {
    cleanupEls.forEach((el) => { if (el.parentNode) el.parentNode.removeChild(el); });
    cleanupEls.length = 0;
  });

  it('focus remains inside the dialog after the waiting card swaps to the normal card', async () => {
    setViewport(1024, 768);

    const steps: CoachStep[] = [
      { selector: '[data-tour="swap-target"]', title: 'Swap Step', body: 'Will appear', waitForTargetTimeout: 5000 },
    ];

    const { container } = render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );

    // Waiting card should be shown, focused
    const dialog = container.querySelector('[role="dialog"]') as HTMLElement;
    expect(dialog).toBeTruthy();
    const waitingCard = dialog.querySelector('[tabindex="-1"]') as HTMLElement;
    expect(waitingCard).toBeTruthy();
    expect(document.activeElement).toBe(waitingCard);

    // Now add the target so it resolves and the card swaps
    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'swap-target');
    targetEl.getBoundingClientRect = () => fakeRect();
    document.body.appendChild(targetEl);
    cleanupEls.push(targetEl);

    // Wait for the swap to happen (waiting text disappears)
    await waitFor(() => {
      expect(screen.queryByText('Waiting for screen to load...')).not.toBeInTheDocument();
    });

    // After the swap, focus should still be on the card (the normal card now)
    const normalCard = dialog.querySelector('[tabindex="-1"]') as HTMLElement;
    expect(normalCard).toBeTruthy();
    expect(document.activeElement).toBe(normalCard);
  });

  it('Tab still wraps inside the dialog after the waiting card swaps to the normal card', async () => {
    setViewport(1024, 768);

    const steps: CoachStep[] = [
      { selector: '[data-tour="swap-tab-target"]', title: 'Swap Tab', body: 'Will appear', waitForTargetTimeout: 5000 },
    ];

    const { container } = render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );

    const dialog = container.querySelector('[role="dialog"]') as HTMLElement;

    // Add target to trigger swap
    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'swap-tab-target');
    targetEl.getBoundingClientRect = () => fakeRect();
    document.body.appendChild(targetEl);
    cleanupEls.push(targetEl);

    // Wait for swap
    await waitFor(() => {
      expect(screen.queryByText('Waiting for screen to load...')).not.toBeInTheDocument();
    });

    // Get all buttons in the dialog after the swap
    const buttons = dialog.querySelectorAll('button');
    expect(buttons.length).toBeGreaterThan(1);

    // Focus the last button
    const lastButton = buttons[buttons.length - 1];
    lastButton.focus();

    // Tab should wrap to the first button
    fireEvent.keyDown(lastButton, { key: 'Tab' });
    expect(document.activeElement).toBe(buttons[0]);

    // Shift+Tab from first should wrap to last
    fireEvent.keyDown(buttons[0], { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(lastButton);
  });

  it('focusin guard redirects focus to the current card after swap', async () => {
    setViewport(1024, 768);

    const steps: CoachStep[] = [
      { selector: '[data-tour="focusin-swap-target"]', title: 'Focusin Swap', body: 'Test', waitForTargetTimeout: 5000 },
    ];

    render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );

    const dialog = screen.getByRole('dialog');

    // Add target to trigger swap
    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'focusin-swap-target');
    targetEl.getBoundingClientRect = () => fakeRect();
    document.body.appendChild(targetEl);
    cleanupEls.push(targetEl);

    // Wait for swap
    await waitFor(() => {
      expect(screen.queryByText('Waiting for screen to load...')).not.toBeInTheDocument();
    });

    // Create an outside element and try to focus it
    const outside = document.createElement('button');
    outside.textContent = 'Outside';
    document.body.appendChild(outside);
    cleanupEls.push(outside);

    outside.focus();

    // Focus should be redirected to the card
    const card = dialog.querySelector('[tabindex="-1"]') as HTMLElement;
    expect(document.activeElement).toBe(card);
  });
});

// =====================================================================
// TEST 4: Reduced-motion mutation-proof tests
// =====================================================================

describe('r12 Reduced-motion: per-call-site mutation proofs', () => {
  const cleanupEls: HTMLElement[] = [];

  afterEach(() => {
    cleanupEls.forEach((el) => { if (el.parentNode) el.parentNode.removeChild(el); });
    cleanupEls.length = 0;
  });

  it('measure off-screen re-scroll uses behavior "auto" under prefers-reduced-motion (line 89 mutation proof)', () => {
    vi.useFakeTimers();
    setViewport(1024, 768);

    // Create a target that is fully off-screen (triggers scrollIntoView in measure)
    const scrollIntoViewSpy = vi.fn();
    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'offscreen-motion');
    targetEl.scrollIntoView = scrollIntoViewSpy;
    // Position it off-screen: bottom < 0
    targetEl.getBoundingClientRect = () => fakeRect({
      top: -200, left: 100, width: 200, height: 50, bottom: -150, right: 300,
    });
    document.body.appendChild(targetEl);
    cleanupEls.push(targetEl);

    const originalMatchMedia = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const steps: CoachStep[] = [
      { selector: '[data-tour="offscreen-motion"]', title: 'Offscreen', body: 'Test' },
    ];

    render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    // Let the initial measure timer fire (280ms) which calls measure()
    act(() => { vi.advanceTimersByTime(300); });

    // scrollIntoView should have been called with behavior: 'auto'
    expect(scrollIntoViewSpy).toHaveBeenCalled();
    const measureCall = scrollIntoViewSpy.mock.calls.find(
      (call: unknown[]) => (call[0] as Record<string, unknown>)?.block === 'center',
    );
    expect(measureCall).toBeTruthy();
    expect((measureCall![0] as Record<string, unknown>).behavior).toBe('auto');

    window.matchMedia = originalMatchMedia;
    vi.useRealTimers();
  });

  it('late-target scroll uses behavior "auto" under prefers-reduced-motion (line 148 mutation proof)', async () => {
    const scrollIntoViewSpy = vi.fn();

    const originalMatchMedia = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const steps: CoachStep[] = [
      { selector: '[data-tour="late-motion-target"]', title: 'Late Motion', body: 'Test', waitForTargetTimeout: 5000 },
    ];

    render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    // Should be waiting
    expect(screen.getByText('Waiting for screen to load...')).toBeInTheDocument();

    // Now add the target with a scrollIntoView spy
    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'late-motion-target');
    targetEl.scrollIntoView = scrollIntoViewSpy;
    targetEl.getBoundingClientRect = () => fakeRect();
    document.body.appendChild(targetEl);
    cleanupEls.push(targetEl);

    // Wait for the target to resolve (MutationObserver fires, then scrollIntoView called)
    await waitFor(() => {
      expect(scrollIntoViewSpy).toHaveBeenCalled();
    });

    const lateTargetCall = scrollIntoViewSpy.mock.calls.find(
      (call: unknown[]) => (call[0] as Record<string, unknown>)?.block === 'center',
    );
    expect(lateTargetCall).toBeTruthy();
    expect((lateTargetCall![0] as Record<string, unknown>).behavior).toBe('auto');

    window.matchMedia = originalMatchMedia;
  });
});