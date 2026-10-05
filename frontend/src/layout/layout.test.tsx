import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from '../App';

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

function mockFetch(body: unknown) {
  return vi.fn().mockImplementation((url: string) => {
    if (url === '/api/health') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    }
    if (url.startsWith('/api/market/')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(marketResponse) });
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

  it('catches min-w-[400px] mutation on the shell root', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));

    Object.defineProperty(window, 'innerWidth', { value: 360, writable: true });

    const { container } = render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    const shellRoot = container.firstElementChild as HTMLElement;
    shellRoot.classList.add('min-w-[400px]');

    const allElements = container.querySelectorAll('*');
    let foundViolation = false;
    allElements.forEach((el) => {
      const widths = getFixedWidthPx(el.className);
      widths.forEach((w) => {
        if (w > 360) foundViolation = true;
      });
    });
    expect(foundViolation).toBe(true);
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