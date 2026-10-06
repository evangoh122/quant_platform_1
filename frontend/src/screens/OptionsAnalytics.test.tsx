import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { OptionsAnalytics } from './OptionsAnalytics';

const mockMarketResponse = {
  symbol: 'NVDA',
  ohlcv: {
    data: [],
    count: 0,
    empty: true,
    source: 'silver_ohlcv_day_adjusted',
    freshness: { state: 'empty', table: 'silver_ohlcv_day_adjusted', detail: '0 rows' },
  },
  options: {
    data: [
      {
        symbol: 'NVDA',
        feature_ts: '2025-09-30',
        iv_atm: 0.45,
        iv_skew: 0.12,
        put_call_ratio: 0.85,
        volume_anomaly_zscore: 2.1,
        put_volume: 50000,
        call_volume: 80000,
      },
    ],
    count: 1,
    empty: false,
    source: 'gold_options_features',
    freshness: { state: 'fresh', table: 'gold_options_features', detail: '1 rows' },
  },
};

describe('OptionsAnalytics', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    window.history.replaceState(null, '', window.location.pathname);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockMarketResponse),
    }));
  });

  it('renders options data on load', async () => {
    render(<OptionsAnalytics />);

    await waitFor(() => {
      expect(screen.getByText('0.4500')).toBeInTheDocument();
    });

    expect(screen.getByText('Options Analytics')).toBeInTheDocument();
  });

  it('skips fetch and shows prompt when symbol is cleared', async () => {
    const user = userEvent.setup();
    render(<OptionsAnalytics />);

    await waitFor(() => {
      expect(screen.getByText('0.4500')).toBeInTheDocument();
    });

    const fetchMock = vi.mocked(fetch);
    const callsBefore = fetchMock.mock.calls.length;

    // Clear the symbol
    const clearBtn = screen.getByLabelText('Clear');
    await user.click(clearBtn);

    await waitFor(() => {
      expect(screen.getByText(/Select a symbol/)).toBeInTheDocument();
    });

    // No new fetch to /api/market/ with empty symbol
    const newCalls = fetchMock.mock.calls.slice(callsBefore);
    for (const call of newCalls) {
      const url = String(call[0]);
      expect(url).not.toMatch(/\/api\/market\/$/);
      expect(url).not.toMatch(/\/api\/market\/%20/);
    }
  });

  it('fetches again when a symbol is picked after clearing', async () => {
    const user = userEvent.setup();
    render(<OptionsAnalytics />);

    await waitFor(() => {
      expect(screen.getByText('0.4500')).toBeInTheDocument();
    });

    // Clear the symbol
    const clearBtn = screen.getByLabelText('Clear');
    await user.click(clearBtn);

    await waitFor(() => {
      expect(screen.getByText(/Select a symbol/)).toBeInTheDocument();
    });

    // Pick AAPL from quick choices
    await user.click(screen.getByText('AAPL', { selector: 'button' }));

    // Should trigger a fetch for AAPL
    await waitFor(() => {
      const fetchMock = vi.mocked(fetch);
      const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
      expect(String(lastCall[0])).toContain('/api/market/AAPL');
    });
  });
});