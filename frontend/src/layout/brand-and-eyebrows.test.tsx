import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import App from '../App';
import { populatedSpreadsResponse } from '../test/spreadsFixture';
import { APPLICATION_TOUR_KEY, AGENT_TOUR_KEY, ARCHITECTURE_TOUR_KEY } from '../components/tours/tourSteps';

/**
 * Design-language guards for the owner's site match.
 *
 * F1 — one brand presentation per viewport. The gold monogram belongs to the
 * top bar; the desktop sidebar and the mobile drawer are navigation-only. The
 * guards below count the actual `.brand-tile` elements the shell renders, so
 * re-adding a tile to the sidebar or the drawer fails them.
 *
 * F2 — an eyebrow names the category of the section, never its title. The
 * site pairs "selected work" with a different title; a verbatim repeat ("paper
 * portfolio" over "IBKR Paper Portfolio") adds nothing. The guard renders every
 * destination and compares each `.eyebrow` with the heading that follows it.
 */

const healthyResponse = {
  status: 'ok',
  version: '1.0.0',
  dependencies: [
    { name: 'lakebase', ok: true, detail: 'connected', latency_ms: 5, last_error: null, last_ok_at: Date.now(), circuit_breaker_state: null },
  ],
  freshness: { state: 'fresh', table: '', detail: '' },
  role_cache_size: 0,
  startup: [],
};

const emptyEnvelope = { data: [], count: 0, empty: true, source: '', freshness: { state: 'empty', table: '', detail: '' } };

function mockFetch() {
  return vi.fn().mockImplementation((url: string) => {
    if (url === '/api/health') return Promise.resolve({ ok: true, json: () => Promise.resolve(healthyResponse) });
    if (url === '/api/health/trace') return Promise.resolve({ ok: true, json: () => Promise.resolve({ slow: [] }) });
    if (url === '/api/analytics') {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          model_performance: emptyEnvelope,
          agent_activity: emptyEnvelope,
          latency: emptyEnvelope,
          stream_freshness: emptyEnvelope,
        }),
      });
    }
    if (url === '/api/sec/coverage') return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [], count: 0, status: 'ok' }) });
    if (url === '/api/portfolio') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ positions: emptyEnvelope, orders: emptyEnvelope }) });
    }
    if (url.startsWith('/api/spreads')) {
      // The eyebrow guard renders every destination; Market Spreads needs a
      // real chart payload so its own eyebrow is compared against the heading
      // that follows it.
      return Promise.resolve({ ok: true, json: () => Promise.resolve(populatedSpreadsResponse) });
    }
    if (url.startsWith('/api/market/')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ symbol: 'NVDA', ohlcv: emptyEnvelope, options: emptyEnvelope }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(emptyEnvelope) });
  });
}

const DESTINATIONS = [
  'Platform Overview',
  'Market Explorer',
  'Market Spreads',
  'Options Analytics',
  'SEC Research',
  'AI Research Agent',
  'Signal Explorer',
  'Strategy Lab',
  'Paper Portfolio',
  'Order Approval',
  'Activity Analytics',
  'System Health',
  'Architecture & Tests',
  'Overview',
  'Data',
  'Infrastructure',
  'Features',
  'Controls',
  'Rubric plan',
];

const DESKTOP_WIDTH = 1440;
const MOBILE_WIDTH = 360;

describe('One brand mark per view', () => {
  const originalInnerWidth = window.innerWidth;

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', mockFetch());
    localStorage.setItem(APPLICATION_TOUR_KEY, '1');
    localStorage.setItem(AGENT_TOUR_KEY, '1');
    localStorage.setItem(ARCHITECTURE_TOUR_KEY, '1');
  });

  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', { value: originalInnerWidth, writable: true, configurable: true });
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('renders exactly one brand tile at desktop width, in the top bar', async () => {
    Object.defineProperty(window, 'innerWidth', { value: DESKTOP_WIDTH, writable: true, configurable: true });

    const { container } = render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    const tiles = container.querySelectorAll('.brand-tile');
    expect(tiles, 'the shell must render one brand tile, not several').toHaveLength(1);

    const header = container.querySelector('header');
    expect(header, 'top bar').toBeTruthy();
    expect(header!.querySelectorAll('.brand-tile')).toHaveLength(1);

    const sidebar = screen.getByRole('complementary');
    expect(sidebar.querySelectorAll('.brand-tile'), 'sidebar is navigation-only').toHaveLength(0);
    expect(within(sidebar).queryByText('QP1')).toBeNull();
    expect(within(sidebar).queryByText('Quant Trading Platform')).toBeNull();

    // The visible wordmark is not duplicated either.
    expect(screen.getAllByText('QP1')).toHaveLength(1);

    // The sidebar stays the primary navigation and the top bar stays exposed.
    expect(within(sidebar).getByRole('button', { name: 'Market Explorer' })).toBeInTheDocument();
    expect(header!.closest('[aria-hidden="true"]')).toBeNull();
    expect(header!.querySelector('.brand-tile')!.className).not.toMatch(/(?:^|\s)hidden(?:\s|$)/);
  });

  it('adds no second brand tile when the mobile drawer opens', async () => {
    Object.defineProperty(window, 'innerWidth', { value: MOBILE_WIDTH, writable: true, configurable: true });
    const user = userEvent.setup();

    const { container } = render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText('Open navigation'));

    const dialog = screen.getByRole('dialog', { name: 'Navigation' });
    expect(dialog.querySelectorAll('.brand-tile')).toHaveLength(0);
    expect(within(dialog).queryByText('QP1')).toBeNull();
    expect(within(dialog).queryByText('Quant Trading Platform')).toBeNull();

    // Still exactly one tile in the document, so no two can ever show together.
    expect(container.querySelectorAll('.brand-tile')).toHaveLength(1);

    // While the drawer is open the top bar (and its mark) is inert rather than
    // duplicated; the drawer carries navigation only.
    const header = container.querySelector('header');
    expect(header!.closest('[aria-hidden="true"]')).not.toBeNull();
    expect(within(dialog).getByRole('button', { name: 'Market Explorer' })).toBeInTheDocument();
  });
});

function normaliseCopy(text: string | null | undefined): string {
  return (text ?? '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function nearestFollowingHeading(el: Element): Element | null {
  for (let node = el.nextElementSibling; node; node = node.nextElementSibling) {
    if (node.matches('h1, h2, h3, h4, h5, h6')) return node;
    const nested = node.querySelector('h1, h2, h3, h4, h5, h6');
    if (nested) return nested;
  }
  const parent = el.parentElement;
  if (!parent || parent === document.body) return null;
  return nearestFollowingHeading(parent);
}

describe('Eyebrow copy never repeats its title', () => {
  const originalInnerWidth = window.innerWidth;

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', mockFetch());
    Object.defineProperty(window, 'innerWidth', { value: DESKTOP_WIDTH, writable: true, configurable: true });
    localStorage.setItem(APPLICATION_TOUR_KEY, '1');
    localStorage.setItem(AGENT_TOUR_KEY, '1');
    localStorage.setItem(ARCHITECTURE_TOUR_KEY, '1');
  });

  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', { value: originalInnerWidth, writable: true, configurable: true });
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('gives every eyebrow a category phrase distinct from its heading on every screen', async () => {
    const user = userEvent.setup();

    const { container } = render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    const sidebar = screen.getByRole('complementary');
    const compared: string[] = [];
    const repeats: string[] = [];

    for (const label of DESTINATIONS) {
      const button = within(sidebar).getByRole('button', { name: label });
      await user.click(button);
      await waitFor(() => {
        expect(button).toHaveAttribute('aria-current', 'page');
      });

      for (const eyebrow of Array.from(container.querySelectorAll('.eyebrow'))) {
        const heading = nearestFollowingHeading(eyebrow);
        if (!heading) continue;

        const eyebrowCopy = normaliseCopy(eyebrow.textContent);
        const headingCopy = normaliseCopy(heading.textContent);
        compared.push(`${label}: "${eyebrowCopy}" / "${headingCopy}"`);
        if (eyebrowCopy === headingCopy) {
          repeats.push(`${label}: <${heading.tagName.toLowerCase()}> repeats its eyebrow "${eyebrowCopy}"`);
        }
      }
    }

    // The guard must actually look at the copy, not pass on an empty page set.
    expect(compared.length).toBeGreaterThanOrEqual(15);
    expect(repeats).toEqual([]);
  });
});
