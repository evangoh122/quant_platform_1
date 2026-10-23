import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import App from '../App';
import { MarketDashboard } from '../screens/MarketDashboard';
import ArchitectureDiagram from '../components/ArchitectureDiagram';
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

  it('no source file declares text below 12px', () => {
    // Covers every way a component can declare a type size: Tailwind arbitrary
    // values and scale classes, `fontSize`/`font-size` declarations (inline
    // style or SVG presentation attribute) and module-level `*_FONT_SIZE`
    // constants. The rendered-scale guard below additionally proves those
    // declared sizes survive SVG viewBox scaling.
    const patterns = [
      /text-\[(\d+(?:\.\d+)?)px\]/g,
      /fontSize:\s*(\d+(?:\.\d+)?)/g,
      /font-size:\s*(\d+(?:\.\d+)?)px/g,
      /\b[A-Z][A-Z0-9_]*_FONT_SIZE\s*=\s*(\d+(?:\.\d+)?)/g,
    ];
    const offenders: string[] = [];
    for (const file of files) {
      const content = readFileSync(file, 'utf-8');
      const rel = file.replace(SRC_DIR + '/', '');
      for (const pattern of patterns) {
        for (const match of content.matchAll(pattern)) {
          if (Number(match[1]) < 12) offenders.push(`${rel}: ${match[0]}`);
        }
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

/**
 * Rendered type floor for SVG text.
 *
 * A 12-unit label is only 12 CSS px while its SVG renders at (or above) the
 * viewBox width. jsdom has no layout engine, so the rendered scale is derived
 * from the sizing that fixes the floor: an SVG that stretches (`w-full`) but
 * declares `min-width` can never render narrower than that minimum, so
 * `scale = minWidth / viewBoxWidth` is the worst case at any viewport. The
 * smallest size a label can actually paint at is
 * `declaredSize * scale` — that, not the authored number, has to clear 12 px.
 */
const TYPE_FLOOR_PX = 12;
const ROOT_FONT_PX = 16; // browser default (index.css only re-states 16 px on phones)

const TAILWIND_TEXT_VARS: Record<string, string> = {
  'text-xs': '--text-xs',
  'text-sm': '--text-sm',
  'text-base': '--text-base',
  'text-lg': '--text-lg',
  'text-xl': '--text-xl',
  'text-2xl': '--text-2xl',
  'text-3xl': '--text-3xl',
};

function pxValue(value: string | null | undefined): number | null {
  if (!value) return null;
  const match = String(value).trim().match(/^(\d+(?:\.\d+)?)(?:px)?$/);
  return match ? Number(match[1]) : null;
}

function cssRemValue(cssVar: string): number | null {
  const match = css.match(new RegExp(`${cssVar}\\s*:\\s*([\\d.]+)rem`));
  return match ? Number(match[1]) * ROOT_FONT_PX : null;
}

function classDeclaredFontSize(el: Element): number | null {
  const cls = typeof el.className === 'string' ? el.className : el.getAttribute('class') ?? '';
  const arbitrary = [...cls.matchAll(/(?:^|\s)text-\[(\d+(?:\.\d+)?)px\]/g)];
  if (arbitrary.length > 0) return Number(arbitrary[arbitrary.length - 1][1]);
  for (const token of cls.split(/\s+/)) {
    if (token === 'text-label') {
      return pxValue((css.match(/\.text-label\s*\{[^}]*font-size:\s*(\d+(?:\.\d+)?)px/) ?? [])[1]);
    }
    const cssVar = TAILWIND_TEXT_VARS[token];
    if (cssVar) return cssRemValue(cssVar);
  }
  return null;
}

/** Nearest declared size on the element or an ancestor `<g>`. jsdom does not
 *  resolve Tailwind classes or presentation attributes, so a missing
 *  declaration is reported as missing instead of silently inheriting 16 px. */
function declaredFontSize(el: Element): number | null {
  let node: Element | null = el;
  while (node) {
    const fromAttribute = pxValue(node.getAttribute('font-size'));
    if (fromAttribute !== null) return fromAttribute;
    const inline = (node as unknown as { style?: CSSStyleDeclaration }).style;
    const fromStyle = pxValue(inline?.fontSize);
    if (fromStyle !== null) return fromStyle;
    const fromClass = classDeclaredFontSize(node);
    if (fromClass !== null) return fromClass;
    node = node.parentElement;
  }
  return null;
}

function svgRenderScale(svg: Element): number {
  const viewBox = svg.getAttribute('viewBox');
  expect(viewBox, 'an SVG containing text must declare a viewBox').toBeTruthy();
  const viewBoxWidth = Number(viewBox!.trim().split(/[\s,]+/)[2]);
  expect(Number.isFinite(viewBoxWidth)).toBe(true);
  expect(viewBoxWidth).toBeGreaterThan(0);

  const classMin = [
    ...(svg.getAttribute('class') ?? '').matchAll(/(?:^|\s)min-w-\[(\d+(?:\.\d+)?)px\]/g),
  ].map((match) => Number(match[1]));
  const inlineMin = pxValue((svg as unknown as { style?: CSSStyleDeclaration }).style?.minWidth);
  const minWidth = inlineMin ?? (classMin.length > 0 ? Math.max(...classMin) : null);
  expect(
    minWidth,
    'a stretching SVG containing text must declare min-width so it cannot shrink below its viewBox',
  ).not.toBeNull();

  return (minWidth as number) / viewBoxWidth;
}

function svgTextOffenders(svg: Element): string[] {
  const scale = svgRenderScale(svg);
  const offenders: string[] = [];
  for (const text of Array.from(svg.querySelectorAll('text'))) {
    const size = declaredFontSize(text);
    const label = (text.textContent ?? '').trim().slice(0, 40);
    if (size === null) {
      offenders.push(`<text>"${label}" declares no size (scale ${scale.toFixed(3)})`);
      continue;
    }
    const rendered = size * scale;
    if (rendered < TYPE_FLOOR_PX) {
      offenders.push(`<text>"${label}" ${size}u x ${scale.toFixed(3)} = ${rendered.toFixed(2)}px`);
    }
  }
  return offenders;
}

const populatedRows = Array.from({ length: 12 }, (_, index) => {
  const day = String(index + 1).padStart(2, '0');
  const close = 100 + index * 2.5;
  return {
    symbol: 'NVDA',
    event_date: `2026-03-${day}`,
    open: close - 1,
    high: close + 2,
    low: close - 2,
    close,
    volume: 1_000_000 + index * 50_000,
    vwap: close - 0.5,
    price_basis: 'adjusted',
  };
});

const populatedMarketResponse = {
  symbol: 'NVDA',
  ohlcv: {
    data: populatedRows,
    count: populatedRows.length,
    empty: false,
    source: 'silver_ohlcv_day_adjusted',
    freshness: { state: 'fresh', table: 'silver_ohlcv_day_adjusted', detail: '12 rows' },
  },
  options: {
    data: [],
    count: 0,
    empty: true,
    source: 'gold_options_features',
    freshness: { state: 'empty', table: 'gold_options_features', detail: '0 rows' },
  },
};

describe('Rendered type floor inside scaled SVG', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(populatedMarketResponse),
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('flags an 11-unit label as a 11 px offender instead of passing vacuously', () => {
    const host = document.createElement('div');
    host.innerHTML =
      '<svg viewBox="0 0 600 200" style="min-width: 600px">' +
      '<text font-size="11">too small</text><text font-size="12">floor</text></svg>';
    const svg = host.querySelector('svg')!;

    const offenders = svgTextOffenders(svg);
    expect(offenders).toHaveLength(1);
    expect(offenders[0]).toContain('11u x 1.000 = 11.00px');

    svg.querySelector('text')!.setAttribute('font-size', '12');
    expect(svgTextOffenders(svg)).toEqual([]);
  });

  it('renders every architecture-diagram label at >= 12 px at its real scale', () => {
    const { container } = render(<ArchitectureDiagram />);
    const svg = container.querySelector('svg');
    expect(svg).toBeTruthy();

    // 34 labels were authored below the floor (and scaled to ~6 px) before
    // this guard: sublabels, PLANNED tags, boundary titles and the legend.
    expect(svg!.querySelectorAll('text').length).toBeGreaterThanOrEqual(30);
    expect(svgTextOffenders(svg!)).toEqual([]);
    expect(svgRenderScale(svg!)).toBeGreaterThanOrEqual(1);
  });

  it('renders every populated market-chart label at >= 12 px at its declared minimum width', async () => {
    const { container } = render(<MarketDashboard />);
    await waitFor(() => {
      expect(container.querySelector('svg[role="img"]')).toBeTruthy();
    });

    const svg = container.querySelector('svg[role="img"]')!;
    const texts = Array.from(svg.querySelectorAll('text'));
    // 5 price-grid labels + 5 date ticks for a 12-row series.
    expect(texts.length).toBeGreaterThanOrEqual(10);
    expect(texts.some((text) => /^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/.test(text.textContent ?? ''))).toBe(true);

    expect(svgTextOffenders(svg)).toEqual([]);
    expect(svgRenderScale(svg)).toBeGreaterThanOrEqual(1);
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

describe('PageHeader tour action at 320 px (r4)', () => {
  const originalInnerWidth = window.innerWidth;

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch());
    localStorage.setItem(APPLICATION_TOUR_KEY, '1');
    localStorage.setItem(AGENT_TOUR_KEY, '1');
    localStorage.setItem(ARCHITECTURE_TOUR_KEY, '1');
    Object.defineProperty(window, 'innerWidth', { value: 320, writable: true, configurable: true });
  });

  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', {
      value: originalInnerWidth,
      writable: true,
      configurable: true,
    });
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('keeps the full Take a tour label in a wrappable, unclipped action', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    const button = screen.getByRole('button', { name: 'Take a tour' });
    const label = within(button).getByText('Take a tour');
    const actionRow = button.parentElement!;

    // The 320 px header must give the action its own row, let the button
    // shrink to it, and wrap the label instead of clipping a nowrap line.
    expect(actionRow.className).toContain('w-full');
    expect(actionRow.className).toContain('min-w-0');
    expect(actionRow.className).toContain('sm:w-auto');
    expect(actionRow.className).toContain('sm:shrink-0');
    expect(button.className).toContain('max-w-full');
    expect(button.className).toContain('min-w-0');
    expect(button.className).not.toContain('truncate');
    expect(label.className).toContain('whitespace-normal');
    expect(label.className).not.toContain('whitespace-nowrap');
    expect(label).toHaveTextContent(/^Take a tour$/);
  });
});
