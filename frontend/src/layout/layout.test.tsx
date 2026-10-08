import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from '../App';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = dirname(fileURLToPath(import.meta.url));
const css: string = readFileSync(join(__dirname, '../index.css'), 'utf-8');

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

const breakerOpenResponse = {
  status: 'ok',
  version: '1.0.0',
  dependencies: [
    { name: 'lakebase', ok: true, detail: 'connected', latency_ms: 5, last_error: null, last_ok_at: Date.now(), circuit_breaker_state: 'open' },
  ],
  freshness: { state: 'fresh', table: '', detail: '' },
  role_cache_size: 0,
  startup: [],
};

const breakerClosedResponse = {
  status: 'ok',
  version: '1.0.0',
  dependencies: [
    { name: 'lakebase', ok: true, detail: 'connected', latency_ms: 5, last_error: null, last_ok_at: Date.now(), circuit_breaker_state: 'closed' },
  ],
  freshness: { state: 'fresh', table: '', detail: '' },
  role_cache_size: 0,
  startup: [],
};

const marketResponse = {
  symbol: 'NVDA',
  ohlcv: { data: [], count: 0, empty: true, source: 'silver_ohlcv_day_adjusted', freshness: { state: 'empty', table: '', detail: '' } },
  options: { data: [], count: 0, empty: true, source: 'gold_options_features', freshness: { state: 'empty', table: '', detail: '' } },
};

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

const signalsResponse = { data: [], count: 0, empty: true, source: '', freshness: { state: 'empty', table: '', detail: '' } };

const chatResponse = { reply: 'No results.', tool_calls: [] };

const secCoverageResponse = { data: [], count: 0, status: 'ok' as const };

function mockFetch(body: unknown) {
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url === '/api/health') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    }
    if (url === '/api/health/trace') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(healthTraceResponse) });
    }
    if (url === '/api/analytics') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(analyticsResponse) });
    }
    if (url.startsWith('/api/market/')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(marketResponse) });
    }
    if (url === '/api/portfolio') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(portfolioResponse) });
    }
    if (url === '/api/signals') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(signalsResponse) });
    }
    if (url === '/api/agent/chat') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(chatResponse) });
    }
    if (url === '/api/sec/coverage') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(secCoverageResponse) });
    }
    if (url.startsWith('/api/orders/')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ order_id: '1', status: 'approved', ok: true }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

describe('Active navigation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('navigates to a non-first destination and updates aria-current in desktop sidebar', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));
    const user = userEvent.setup();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    // Initially, Platform Overview has aria-current
    const overviewButton = screen.getByRole('button', { name: 'Platform Overview' });
    expect(overviewButton).toHaveAttribute('aria-current', 'page');

    // Navigate to Market Explorer
    const marketButton = screen.getByRole('button', { name: 'Market Explorer' });
    await user.click(marketButton);

    // Now Market Explorer should have aria-current
    await waitFor(() => {
      expect(marketButton).toHaveAttribute('aria-current', 'page');
    });

    // Platform Overview should NOT have aria-current
    expect(overviewButton).not.toHaveAttribute('aria-current');
  });

  it('navigates to a non-first destination and updates aria-current in mobile drawer', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));
    const user = userEvent.setup();

    // Mock window.innerWidth for mobile
    Object.defineProperty(window, 'innerWidth', { value: 360, writable: true });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    // Open drawer
    const menuButton = screen.getByLabelText('Open navigation');
    await user.click(menuButton);

    const dialog = screen.getByRole('dialog', { name: 'Navigation' });
    expect(dialog).toBeInTheDocument();

    // Initially, Platform Overview has aria-current in the drawer
    const overviewButton = dialog.querySelector('button[aria-current="page"]');
    expect(overviewButton?.textContent).toBe('Platform Overview');

    // Navigate to Market Explorer in the drawer
    const marketButton = within(dialog).getByRole('button', { name: 'Market Explorer' });
    await user.click(marketButton);

    // Drawer should close after navigation
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Navigation' })).not.toBeInTheDocument();
    });

    // Re-open drawer to check aria-current
    const menuButton2 = screen.getByLabelText('Open navigation');
    await user.click(menuButton2);

    const dialog2 = screen.getByRole('dialog', { name: 'Navigation' });
    const activeButton = dialog2.querySelector('button[aria-current="page"]');
    expect(activeButton?.textContent).toBe('Market Explorer');
  });
});

describe('Mobile navigation accessibility', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('does not steal focus on initial render when drawer is closed', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));
    Object.defineProperty(window, 'innerWidth', { value: 360, writable: true });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    const trigger = screen.getByLabelText('Open navigation');
    expect(document.activeElement).not.toBe(trigger);
  });

  it('restores focus to trigger after closing the drawer', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));
    const user = userEvent.setup();
    Object.defineProperty(window, 'innerWidth', { value: 360, writable: true });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    const trigger = screen.getByLabelText('Open navigation');
    await user.click(trigger);

    const dialog = screen.getByRole('dialog', { name: 'Navigation' });
    expect(dialog).toBeInTheDocument();

    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Navigation' })).not.toBeInTheDocument();
    });

    expect(document.activeElement).toBe(trigger);
  });

  it('drawer has aria-modal="true"', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));
    const user = userEvent.setup();
    Object.defineProperty(window, 'innerWidth', { value: 360, writable: true });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText('Open navigation'));

    const dialog = screen.getByRole('dialog', { name: 'Navigation' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('traps Tab inside the drawer while open', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));
    const user = userEvent.setup();
    Object.defineProperty(window, 'innerWidth', { value: 360, writable: true });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText('Open navigation'));

    const dialog = screen.getByRole('dialog', { name: 'Navigation' });
    const buttons = dialog.querySelectorAll('button');
    const lastButton = buttons[buttons.length - 1];

    lastButton.focus();
    await user.keyboard('{Tab}');

    expect(dialog.contains(document.activeElement)).toBe(true);
  });
});

describe('Breaker rule', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows banner when lakebase ok but circuit_breaker_state is open', async () => {
    vi.stubGlobal('fetch', mockFetch(breakerOpenResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    expect(screen.getByText(/Account services unavailable/)).toBeInTheDocument();
  });

  it('hides banner when lakebase ok and circuit_breaker_state is closed', async () => {
    vi.stubGlobal('fetch', mockFetch(breakerClosedResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    expect(screen.queryByText(/Account services unavailable/)).not.toBeInTheDocument();
  });
});

describe('Collapsed sidebar accessibility', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('preserves full accessible name on collapsed nav buttons via aria-label', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));
    const user = userEvent.setup();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    const collapseBtn = screen.getByLabelText('Collapse sidebar');
    await user.click(collapseBtn);

    const marketButton = screen.getByRole('button', { name: 'Market Explorer' });
    expect(marketButton).toHaveAttribute('aria-label', 'Market Explorer');
    expect(marketButton.textContent).toBe('M');
  });
});

const ALL_DESTINATIONS = [
  { id: 'platform-overview', label: 'Platform Overview' },
  { id: 'market', label: 'Market Explorer' },
  { id: 'options', label: 'Options Analytics' },
  { id: 'sec', label: 'SEC Research' },
  { id: 'agent', label: 'AI Research Agent' },
  { id: 'signals', label: 'Signal Explorer' },
  { id: 'strategy-lab', label: 'Strategy Lab' },
  { id: 'portfolio', label: 'Paper Portfolio' },
  { id: 'orders', label: 'Order Approval' },
  { id: 'analytics', label: 'Activity Analytics' },
  { id: 'health', label: 'System Health' },
  { id: 'architecture', label: 'Architecture & Tests' },
];

describe('Navigation destination enumeration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders every destination label from production NAV_GROUPS', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    for (const dest of ALL_DESTINATIONS) {
      expect(screen.getByRole('button', { name: dest.label })).toBeInTheDocument();
    }
  });

  it('navigates to each destination on click and preserves aria-current', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));
    const user = userEvent.setup();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    for (const dest of ALL_DESTINATIONS) {
      const button = screen.getByRole('button', { name: dest.label });
      await user.click(button);

      await waitFor(() => {
        expect(button).toHaveAttribute('aria-current', 'page');
      });
    }
  });

  it('renders Options Analytics as a production navigation button', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: 'Options Analytics' })).toBeInTheDocument();
  });
});

describe('Strategy Lab destination', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders Strategy Lab as a navigation destination', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: 'Strategy Lab' })).toBeInTheDocument();
  });

  it('navigates to Strategy Lab placeholder on click', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));
    const user = userEvent.setup();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    const button = screen.getByRole('button', { name: 'Strategy Lab' });
    await user.click(button);

    await waitFor(() => {
      expect(button).toHaveAttribute('aria-current', 'page');
    });

    expect(screen.getByRole('heading', { name: 'Strategy Lab' })).toBeInTheDocument();
    expect(screen.getByText(/Coming in a future delivery round/)).toBeInTheDocument();
  });
});

describe('Environment badge', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders an environment badge in the header', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    const badge = screen.getByTestId('env-badge');
    expect(badge).toBeInTheDocument();
    expect(badge.textContent).toMatch(/dev|staging|prod/);
  });
});

describe('360px contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  function getFixedWidthPx(className: string): number[] {
    const matches = className.matchAll(/(?:^|\s)(?:w|min-w)-\[(\d+)px\]/g);
    return [...matches].map((m) => parseInt(m[1], 10));
  }

  it('enforces layout contract at 360px viewport width', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));

    Object.defineProperty(window, 'innerWidth', { value: 360, writable: true });

    const { container } = render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    const allElements = container.querySelectorAll('*');
    allElements.forEach((el) => {
      const widths = getFixedWidthPx(el.className);
      widths.forEach((w) => {
        expect(w).toBeLessThanOrEqual(360);
      });
    });

    const mainContent = container.querySelector('main');
    expect(mainContent).toBeTruthy();
    expect(mainContent!.className).toContain('min-w-0');

    const flexContainer = container.querySelector('.min-w-0.flex-1.flex-col');
    expect(flexContainer).toBeTruthy();
  });

  it('wraps real tables in horizontally scrollable containers', async () => {
    const marketWithData = {
      symbol: 'NVDA',
      ohlcv: {
        data: [{ symbol: 'NVDA', event_date: '2025-01-01', open: 100, high: 110, low: 95, close: 105, volume: 1000000, vwap: 102.5 }],
        count: 1,
        empty: false,
        source: 'silver_ohlcv_day_adjusted',
        freshness: { state: 'fresh', table: '', detail: '' },
      },
      options: { data: [], count: 0, empty: true, source: 'gold_options_features', freshness: { state: 'empty', table: '', detail: '' } },
    };
    const fetchWithData = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/health') return Promise.resolve({ ok: true, json: () => Promise.resolve(healthyResponse) });
      if (url.startsWith('/api/market/')) return Promise.resolve({ ok: true, json: () => Promise.resolve(marketWithData) });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchWithData);
    const user = userEvent.setup();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Market Explorer' }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Market Explorer' })).toBeInTheDocument();
    });

    const tables = document.querySelectorAll('table');
    expect(tables.length).toBeGreaterThan(0);

    tables.forEach((table) => {
      const parent = table.parentElement;
      expect(parent).toBeTruthy();
      expect(parent!.className).toMatch(/overflow-x-auto|overflow-x-scroll/);
    });
  });
});

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  return [
    parseInt(h.substring(0, 2), 16),
    parseInt(h.substring(2, 4), 16),
    parseInt(h.substring(4, 6), 16),
  ];
}

function relativeLuminance([r, g, b]: [number, number, number]): number {
  const [rs, gs, bs] = [r, g, b].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
}

function contrastRatio(fg: string, bg: string): number {
  const l1 = Math.max(relativeLuminance(hexToRgb(fg)), relativeLuminance(hexToRgb(bg)));
  const l2 = Math.min(relativeLuminance(hexToRgb(fg)), relativeLuminance(hexToRgb(bg)));
  return (l1 + 0.05) / (l2 + 0.05);
}

function parseCssVar(raw: string, name: string): string {
  const match = raw.match(new RegExp(`${name}\\s*:\\s*(#[0-9a-fA-F]{6})`));
  if (!match) throw new Error(`CSS variable ${name} not found`);
  return match[1];
}

const SURFACE = parseCssVar(css, '--surface');
const TEXT_MUTED = parseCssVar(css, '--text-muted');
const WARNING = parseCssVar(css, '--warning');

describe('WCAG AA contrast tokens', () => {
  it('--text-muted meets 4.5:1 on --surface', () => {
    expect(contrastRatio(TEXT_MUTED, SURFACE)).toBeGreaterThanOrEqual(4.5);
  });

  it('--warning text meets 4.5:1 on --surface', () => {
    expect(contrastRatio(WARNING, SURFACE)).toBeGreaterThanOrEqual(4.5);
  });
});