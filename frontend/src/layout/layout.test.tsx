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

describe('360px contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('enforces layout contract at 360px viewport width', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));

    // Mock window.innerWidth for mobile
    Object.defineProperty(window, 'innerWidth', { value: 360, writable: true });

    const { container } = render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    // Check that the shell header does not have a fixed width class like w-[400px]
    const header = container.querySelector('header');
    expect(header).toBeTruthy();
    expect(header!.className).not.toContain('w-[400px]');
    expect(header!.className).not.toMatch(/\bw-\[\d+px\]/);

    // Check that main content uses min-w-0
    const mainContent = container.querySelector('main');
    expect(mainContent).toBeTruthy();
    expect(mainContent!.className).toContain('min-w-0');

    // Check that the flex container uses min-w-0
    const flexContainer = container.querySelector('.min-w-0.flex-1.flex-col');
    expect(flexContainer).toBeTruthy();

    // Check that tables are wrapped in horizontally scrollable containers
    const tables = container.querySelectorAll('table');
    tables.forEach((table) => {
      const parent = table.parentElement;
      expect(parent).toBeTruthy();
      expect(parent!.className).toMatch(/overflow-x-auto|overflow-x-scroll/);
    });
  });
});