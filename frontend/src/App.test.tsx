import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from './App';

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
      expect(screen.getByRole('heading', { name: 'Market Dashboard' })).toBeInTheDocument();
    });

    expect(screen.queryByText(/Account services unavailable/)).not.toBeInTheDocument();
  });
});