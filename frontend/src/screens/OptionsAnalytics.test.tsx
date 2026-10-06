import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { OptionsAnalytics } from './OptionsAnalytics';

const mockOptionsResponse = {
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
        feature_ts: '2026-08-01T00:00:00Z',
        put_volume: 1000,
        call_volume: 2000,
        put_call_ratio: 0.5,
        iv_atm: null,
        iv_25d_put: null,
        iv_25d_call: null,
        iv_skew: null,
        iv_term_slope: null,
        avg_spread_pct: null,
        volume_anomaly_zscore: 1.2,
        oi_concentration: null,
        net_delta_exposure: null,
      },
      {
        symbol: 'NVDA',
        feature_ts: '2026-08-02T00:00:00Z',
        put_volume: 1500,
        call_volume: 1800,
        put_call_ratio: 0.833,
        iv_atm: null,
        iv_25d_put: null,
        iv_25d_call: null,
        iv_skew: null,
        iv_term_slope: null,
        avg_spread_pct: null,
        volume_anomaly_zscore: -0.5,
        oi_concentration: null,
        net_delta_exposure: null,
      },
      {
        symbol: 'NVDA',
        feature_ts: '2026-08-03T00:00:00Z',
        put_volume: 1200,
        call_volume: 2200,
        put_call_ratio: 0.545,
        iv_atm: 0.3456,
        iv_25d_put: 0.32,
        iv_25d_call: 0.37,
        iv_skew: 0.05,
        iv_term_slope: 0.02,
        avg_spread_pct: null,
        volume_anomaly_zscore: 2.1,
        oi_concentration: null,
        net_delta_exposure: null,
      },
    ],
    count: 3,
    empty: false,
    source: 'gold_options_features',
    freshness: { state: 'fresh', table: 'gold_options_features', detail: '3 rows' },
  },
};

const emptyOptionsResponse = {
  symbol: 'NVDA',
  ohlcv: {
    data: [],
    count: 0,
    empty: true,
    source: 'silver_ohlcv_day_adjusted',
    freshness: { state: 'empty', table: 'silver_ohlcv_day_adjusted', detail: '0 rows' },
  },
  options: {
    data: [],
    count: 0,
    empty: true,
    source: 'gold_options_features',
    freshness: { state: 'empty', table: 'gold_options_features', detail: '0 rows' },
  },
};

describe('OptionsAnalytics', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows IV stat with date from the last row that has IV, no IV line charted', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockOptionsResponse),
    }));

    render(<OptionsAnalytics />);

    await waitFor(() => {
      expect(screen.getByText('0.3456')).toBeInTheDocument();
    });

    // IV stat should show the date (appears in stat tile, chart axis, and table)
    expect(screen.getAllByText(/Aug 3/).length).toBeGreaterThanOrEqual(1);

    // The chart should be rendered
    const chart = screen.getByRole('img', { name: /options put\/call timeline/i });
    expect(chart).toBeInTheDocument();

    // The legend should NOT have an IV ATM entry (IV is not charted as time series)
    expect(screen.queryByText(/IV ATM/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/iv_atm/i)).not.toBeInTheDocument();
  });

  it('draws the put/call ratio line', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockOptionsResponse),
    }));

    render(<OptionsAnalytics />);

    await waitFor(() => {
      expect(screen.getAllByText(/P\/C Ratio/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders data-table fallback listing the rows', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockOptionsResponse),
    }));

    render(<OptionsAnalytics />);

    await waitFor(() => {
      expect(screen.getByText('View data table')).toBeInTheDocument();
    });

    const summary = screen.getByText('View data table');
    expect(summary.tagName.toLowerCase()).toBe('summary');
  });

  it('shows empty state when options data is empty', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(emptyOptionsResponse),
    }));

    render(<OptionsAnalytics />);

    await waitFor(() => {
      expect(screen.getAllByText(/No options features yet/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows error state on API failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    }));

    render(<OptionsAnalytics />);

    await waitFor(() => {
      expect(screen.getByText(/Something went wrong/)).toBeInTheDocument();
    });
  });
});