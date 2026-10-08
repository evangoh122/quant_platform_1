import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from './App';
import { markTourSeen } from './components/tours/TourHost';
import { APPLICATION_TOUR_KEY } from './components/tours/tourSteps';

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

const degradedResponse = {
  status: 'degraded',
  version: '1.0.0',
  dependencies: [
    { name: 'lakebase', ok: false, detail: 'connection refused', latency_ms: null, last_error: 'ECONNREFUSED', last_ok_at: null, circuit_breaker_state: 'open' },
  ],
  freshness: { state: 'unavailable', table: '', detail: '' },
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

describe('App shell and navigation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders grouped navigation and a default Platform Overview destination', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: 'Platform Overview' })).toBeInTheDocument();
    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Research')).toBeInTheDocument();
    expect(screen.getByText('Strategy')).toBeInTheDocument();
    expect(screen.getByText('Operations')).toBeInTheDocument();
    expect(screen.getByText('Evidence')).toBeInTheDocument();
  });

  it('marks the selected destination with an accessible active state', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    const overviewButton = screen.getByRole('button', { name: 'Platform Overview' });
    expect(overviewButton).toHaveAttribute('aria-current', 'page');

    const marketButton = screen.getByRole('button', { name: 'Market Explorer' });
    expect(marketButton).not.toHaveAttribute('aria-current');
  });

  it('opens and closes the mobile drawer with keyboard controls', async () => {
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

    expect(screen.getByRole('dialog', { name: 'Navigation' })).toBeInTheDocument();

    // Close with Escape
    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Navigation' })).not.toBeInTheDocument();
    });
  });

  it('keeps the Lakebase banner visible when the breaker is open', async () => {
    vi.stubGlobal('fetch', mockFetch(degradedResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    expect(screen.getByText(/Account services unavailable/)).toBeInTheDocument();
  });

  it('exposes a visible header Take a tour action and shell tour targets', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: 'Take a tour' })).toBeInTheDocument();
    expect(document.querySelector('[data-tour="navigation"]')).toBeInTheDocument();
    expect(document.querySelector('[data-tour="tour-action"]')).toBeInTheDocument();
  });

  it('exposes the lakebase-banner tour target when the banner is visible', async () => {
    vi.stubGlobal('fetch', mockFetch(degradedResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    expect(document.querySelector('[data-tour="lakebase-banner"]')).toBeInTheDocument();
  });

  it('opens the tour dialog when Take a tour is clicked', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));
    markTourSeen('qp_tour_application_v1');
    markTourSeen('qp_tour_agent_v1');
    markTourSeen('qp_tour_architecture_v1');
    const user = userEvent.setup();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    expect(screen.queryByRole('dialog', { name: 'Guided tour' })).not.toBeInTheDocument();

    const tourButton = screen.getByRole('button', { name: 'Take a tour' });
    await user.click(tourButton);

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'Guided tour' })).toBeInTheDocument();
    });
  });

  it('opens the tour dialog when Take a tour is clicked even if already seen', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));
    markTourSeen('qp_tour_application_v1');
    const user = userEvent.setup();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    expect(screen.queryByRole('dialog', { name: 'Guided tour' })).not.toBeInTheDocument();

    const tourButton = screen.getByRole('button', { name: 'Take a tour' });
    await user.click(tourButton);

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'Guided tour' })).toBeInTheDocument();
    });
  });
});

describe('App health banner', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows banner when Lakebase is degraded / breaker open', async () => {
    vi.stubGlobal('fetch', mockFetch(degradedResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Account services unavailable/)).toBeInTheDocument();
    });
  });

  it('hides banner when health is ok', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    expect(screen.queryByText(/Account services unavailable/)).not.toBeInTheDocument();
  });
});

describe('App — agent tour auto-start guard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('does not auto-start agent tour on Platform Overview when application tour is seen', async () => {
    vi.stubGlobal('fetch', mockFetch(healthyResponse));
    markTourSeen(APPLICATION_TOUR_KEY);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    // Wait past the 600 ms auto-start delay — agent tour must NOT appear
    await new Promise((r) => setTimeout(r, 1000));

    expect(screen.queryByText('Research Agent tour')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Guided tour' })).not.toBeInTheDocument();
  });
});