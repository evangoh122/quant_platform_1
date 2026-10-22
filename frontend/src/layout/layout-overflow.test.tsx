import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import App from '../App';
import { APPLICATION_TOUR_KEY, AGENT_TOUR_KEY, ARCHITECTURE_TOUR_KEY } from '../components/tours/tourSteps';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC_DIR = join(__dirname, '..');
const css: string = readFileSync(join(SRC_DIR, 'index.css'), 'utf-8');

/**
 * Mobile-overflow guard.
 *
 * The reported bug: at phone widths the hero row and every card were wider
 * than the viewport, so text was clipped on the right. The cause is that the
 * shell had no horizontal clamp and no centred, max-width content column, so a
 * single child whose min-content width exceeded the viewport (the three-button
 * hero row, a `nowrap` label, a wide chart/diagram, a long id) widened the
 * whole document and every block-level card inside it.
 *
 * jsdom has no layout engine, so these tests assert the structural guarantees
 * that keep the page inside the viewport (the shell guard, the content column,
 * `min-w-0` on flexible children, wrapping space-between rows, fixed widths
 * only inside scroll regions) plus the CSS/source rules behind them. The manual
 * browser check is documented in .agents/evidence/BUILD-frontend-evangoh-match.md.
 */

const VIEWPORTS = [320, 375, 390, 768];

const DESTINATIONS = [
  'Platform Overview',
  'Market Explorer',
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

const emptyEnvelope = { data: [], count: 0, empty: true, source: '', freshness: { state: 'empty', table: '', detail: '' } };

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
    if (url.startsWith('/api/market/')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ symbol: 'NVDA', ohlcv: emptyEnvelope, options: emptyEnvelope }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(emptyEnvelope) });
  });
}

function fixedClassWidths(className: string): number[] {
  const matches = className.matchAll(/(?:^|\s)(?:w|min-w)-\[(\d+)px\]/g);
  return [...matches].map((m) => parseInt(m[1], 10));
}

function isScrollRegion(el: Element | null): boolean {
  let node: Element | null = el;
  while (node) {
    const cls = typeof node.className === 'string' ? node.className : '';
    if (/overflow-x-auto|overflow-x-scroll|data-table-wrap|overflow-auto/.test(cls)) return true;
    node = node.parentElement;
  }
  return false;
}

function assertViewportGuards(container: HTMLElement, width: number, context: string) {
  const shell = container.querySelector('.app-shell');
  expect(shell, `${context}: app shell`).toBeTruthy();
  expect(shell!.className, `${context}: shell horizontal guard`).toContain('overflow-x-clip');

  const main = container.querySelector('main');
  expect(main, `${context}: main`).toBeTruthy();
  expect(main!.className, `${context}: main min-w-0`).toContain('min-w-0');

  const column = main!.querySelector('.content-column');
  expect(column, `${context}: content column`).toBeTruthy();

  const wide: string[] = [];
  container.querySelectorAll('*').forEach((el) => {
    const cls = typeof el.className === 'string' ? el.className : '';
    for (const px of fixedClassWidths(cls)) {
      if (px > width && !isScrollRegion(el)) wide.push(`${el.tagName.toLowerCase()} w=${px} class="${cls.slice(0, 80)}"`);
    }
    const inlineMin = el instanceof HTMLElement ? el.style.minWidth : '';
    const inlineMatch = inlineMin.match(/^(\d+)px$/);
    if (inlineMatch && parseInt(inlineMatch[1], 10) > width && !isScrollRegion(el)) {
      wide.push(`${el.tagName.toLowerCase()} inline min-width=${inlineMin}`);
    }
  });
  expect(wide, `${context}: fixed widths wider than ${width}px must sit inside a scroll region`).toEqual([]);

  // Space-between rows must be able to wrap; a non-wrapping row is what pushed
  // the screen header and title rows out of the viewport.
  const rigid: string[] = [];
  container.querySelectorAll('*').forEach((el) => {
    const cls = typeof el.className === 'string' ? el.className : '';
    if (!/(?:^|\s)flex(?:-\w+)?\b/.test(cls)) return;
    if (!/(?:^|\s)justify-between\b/.test(cls)) return;
    if (/(?:^|\s)flex-wrap\b/.test(cls)) return;
    rigid.push(`${el.tagName.toLowerCase()} class="${cls.slice(0, 90)}"`);
  });
  expect(rigid, `${context}: justify-between rows must wrap`).toEqual([]);
}

describe('Horizontal overflow guards on every screen', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', mockFetch());
    localStorage.setItem(APPLICATION_TOUR_KEY, '1');
    localStorage.setItem(AGENT_TOUR_KEY, '1');
    localStorage.setItem(ARCHITECTURE_TOUR_KEY, '1');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  for (const width of VIEWPORTS) {
    it(`keeps every screen inside a ${width}px viewport`, async () => {
      Object.defineProperty(window, 'innerWidth', { value: width, writable: true, configurable: true });
      const user = userEvent.setup();

      const { container } = render(<App />);

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
      });

      assertViewportGuards(container, width, `platform-overview @${width}`);

      const sidebar = screen.getByRole('complementary');
      for (const label of DESTINATIONS) {
        const button = within(sidebar).getByRole('button', { name: label });
        await user.click(button);
        await waitFor(() => {
          expect(button).toHaveAttribute('aria-current', 'page');
        });
        assertViewportGuards(container, width, `${label} @${width}`);
      }
    });
  }
});

describe('CSS-level overflow and type floors', () => {
  it('clamps horizontal scrolling at the document and shell level', () => {
    expect(css).toMatch(/html\s*\{[^}]*overflow-x:\s*clip/);
    expect(css).toMatch(/body\s*\{[^}]*overflow-x:\s*clip/);
    expect(css).toMatch(/\.app-shell\s*\{[^}]*overflow-x:\s*clip/);
  });

  it('defines one centred content column with a max width', () => {
    expect(css).toMatch(/--content-max:\s*\d+px/);
    expect(css).toMatch(/\.content-column\s*\{[^}]*max-width:\s*var\(--content-max\)/);
    expect(css).toMatch(/\.content-column\s*\{[^}]*min-width:\s*0/);
  });

  it('defines the site eyebrow, featured card and mono label primitives', () => {
    expect(css).toMatch(/--font-serif:\s*"Georgia"/);
    expect(css).toMatch(/\.eyebrow\s*\{[^}]*font-family:\s*var\(--font-serif\)/);
    expect(css).toMatch(/\.eyebrow\s*\{[^}]*font-style:\s*italic/);
    expect(css).toMatch(/\.card-featured\s*\{[^}]*radial-gradient/);
    expect(css).toMatch(/\.text-label\s*\{[^}]*font-size:\s*12px/);
  });

  it('keeps the mobile touch-target and reduced-motion guards intact', () => {
    expect(css).toMatch(/@media\s*\(max-width:\s*767px\)[\s\S]*min-height:\s*44px/);
    expect(css).toMatch(/@media\s*\(pointer:\s*coarse\)[\s\S]*var\(--touch-target\)/);
    expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
    expect(css).toMatch(/@media\s*\(prefers-contrast:\s*more\)/);
    expect(css).toMatch(/:where\(button, a, input, select, textarea, summary, \[role="button"\]\):focus-visible/);
  });
});

function walkTsx(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      files.push(...walkTsx(full));
    } else if (entry.endsWith('.tsx') && !entry.includes('.test.')) {
      files.push(full);
    }
  }
  return files;
}

describe('Source floors: type size and fixed widths', () => {
  const files = walkTsx(SRC_DIR);

  it('no source file renders text below 12px', () => {
    const offenders: string[] = [];
    for (const file of files) {
      const content = readFileSync(file, 'utf-8');
      const rel = file.replace(SRC_DIR + '/', '');
      for (const match of content.matchAll(/text-\[(\d+)px\]/g)) {
        if (parseInt(match[1], 10) < 12) offenders.push(`${rel}: ${match[0]}`);
      }
      for (const match of content.matchAll(/fontSize:\s*(\d+)/g)) {
        if (parseInt(match[1], 10) < 12) offenders.push(`${rel}: fontSize ${match[1]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('wide fixed widths only exist inside a horizontal scroll region in the same file', () => {
    const offenders: string[] = [];
    for (const file of files) {
      const content = readFileSync(file, 'utf-8');
      const rel = file.replace(SRC_DIR + '/', '');
      const scoped = /overflow-x-auto/.test(content);
      for (const match of content.matchAll(/(?:min-)?w-\[(\d+)px\]/g)) {
        if (parseInt(match[1], 10) > 320 && !scoped) offenders.push(`${rel}: ${match[0]}`);
      }
      for (const match of content.matchAll(/minWidth:\s*(\d+)/g)) {
        if (parseInt(match[1], 10) > 320 && !scoped) offenders.push(`${rel}: minWidth ${match[1]}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe('First-run tour on mobile', () => {
  const originalMatchMedia = window.matchMedia;
  const originalInnerWidth = window.innerWidth;

  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal('fetch', mockFetch());
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === '(max-width: 767px)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    Object.defineProperty(window, 'innerWidth', { value: 390, writable: true, configurable: true });
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    Object.defineProperty(window, 'innerWidth', { value: originalInnerWidth, writable: true, configurable: true });
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('does not auto-open the dimming tour on a phone-width viewport', async () => {
    vi.useFakeTimers();
    try {
      render(<App />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(screen.queryByRole('dialog', { name: 'Guided tour' })).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('still opens the tour from the header action on a phone-width viewport', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Take a tour' }));

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'Guided tour' })).toBeInTheDocument();
    });
  });
});
