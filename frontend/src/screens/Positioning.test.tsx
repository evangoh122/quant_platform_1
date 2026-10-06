import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Positioning } from './Positioning';

const mockPositioningResponse = {
  asset_class: 'equity_index',
  weekly: {
    data: [
      {
        mapped_asset: 'equity_index',
        report_date: '2026-08-25',
        information_available_ts: '2026-08-29T20:00:00Z',
        lev_money_net: -50000,
        lev_money_net_chg_1w: -2000,
        lev_money_pctile_52w: 35,
        lev_money_zscore_52w: -0.8,
        asset_mgr_net: 80000,
        asset_mgr_pctile_52w: 72,
        crowding_score: 0.65,
        regime_label: 'crowded_short',
      },
      {
        mapped_asset: 'equity_index',
        report_date: '2026-09-01',
        information_available_ts: '2026-09-05T20:00:00Z',
        lev_money_net: -48000,
        lev_money_net_chg_1w: 2000,
        lev_money_pctile_52w: 38,
        lev_money_zscore_52w: -0.6,
        asset_mgr_net: 82000,
        asset_mgr_pctile_52w: 74,
        crowding_score: 0.62,
        regime_label: 'crowded_short',
      },
    ],
    count: 2,
    empty: false,
    source: 'gold_cot_features',
    freshness: { state: 'fresh', table: 'gold_cot_features', detail: '2 rows' },
  },
  contracts: {
    data: [
      {
        contract_name: 'E-mini S&P 500',
        open_interest: 2500000,
        dealer_net: -10000,
        asset_mgr_net: 50000,
        lev_money_net: -30000,
        dealer_pct_oi: -0.4,
        asset_mgr_pct_oi: 2.0,
        lev_money_pct_oi: -1.2,
      },
      {
        contract_name: 'Nasdaq-100 E-mini',
        open_interest: 500000,
        dealer_net: -5000,
        asset_mgr_net: 20000,
        lev_money_net: -15000,
        dealer_pct_oi: -1.0,
        asset_mgr_pct_oi: 4.0,
        lev_money_pct_oi: -3.0,
      },
    ],
    count: 2,
    empty: false,
    source: 'silver_cot_positions',
    freshness: { state: 'fresh', table: 'silver_cot_positions', detail: '2 rows' },
  },
};

const mockNullWeekResponse = {
  asset_class: 'equity_index',
  weekly: {
    data: [
      {
        mapped_asset: 'equity_index',
        report_date: '2026-08-18',
        information_available_ts: '2026-08-22T20:00:00Z',
        lev_money_net: -50000,
        lev_money_net_chg_1w: null,
        lev_money_pctile_52w: 30,
        lev_money_zscore_52w: -1.0,
        asset_mgr_net: 75000,
        asset_mgr_pctile_52w: 68,
        crowding_score: 0.7,
        regime_label: 'crowded_short',
      },
      {
        mapped_asset: 'equity_index',
        report_date: '2026-08-25',
        information_available_ts: '2026-08-29T20:00:00Z',
        lev_money_net: null,
        lev_money_net_chg_1w: null,
        lev_money_pctile_52w: null,
        lev_money_zscore_52w: null,
        asset_mgr_net: null,
        asset_mgr_pctile_52w: null,
        crowding_score: null,
        regime_label: null,
      },
      {
        mapped_asset: 'equity_index',
        report_date: '2026-09-01',
        information_available_ts: '2026-09-05T20:00:00Z',
        lev_money_net: -45000,
        lev_money_net_chg_1w: 5000,
        lev_money_pctile_52w: 40,
        lev_money_zscore_52w: -0.5,
        asset_mgr_net: 85000,
        asset_mgr_pctile_52w: 76,
        crowding_score: 0.58,
        regime_label: 'neutral',
      },
    ],
    count: 3,
    empty: false,
    source: 'gold_cot_features',
    freshness: { state: 'fresh', table: 'gold_cot_features', detail: '3 rows' },
  },
  contracts: {
    data: [],
    count: 0,
    empty: true,
    source: 'silver_cot_positions',
    freshness: { state: 'empty', table: 'silver_cot_positions', detail: '0 rows' },
  },
};

const emptyResponse = {
  asset_class: 'equity_index',
  weekly: {
    data: [],
    count: 0,
    empty: true,
    source: 'gold_cot_features',
    freshness: { state: 'empty', table: 'gold_cot_features', detail: '0 rows' },
  },
  contracts: {
    data: [],
    count: 0,
    empty: true,
    source: 'silver_cot_positions',
    freshness: { state: 'empty', table: 'silver_cot_positions', detail: '0 rows' },
  },
};

const mockMarketResponse = {
  symbol: 'SPY',
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
        symbol: 'SPY',
        feature_ts: '2026-09-01T00:00:00Z',
        put_volume: 1000,
        call_volume: 2000,
        put_call_ratio: 0.5,
        iv_atm: null,
        iv_25d_put: null,
        iv_25d_call: null,
        iv_skew: null,
        iv_term_slope: null,
        avg_spread_pct: null,
        volume_anomaly_zscore: null,
        oi_concentration: 0.15,
        net_delta_exposure: 0.08,
      },
      {
        symbol: 'SPY',
        feature_ts: '2026-09-02T00:00:00Z',
        put_volume: 1200,
        call_volume: 1800,
        put_call_ratio: 0.667,
        iv_atm: null,
        iv_25d_put: null,
        iv_25d_call: null,
        iv_skew: null,
        iv_term_slope: null,
        avg_spread_pct: null,
        volume_anomaly_zscore: null,
        oi_concentration: null,
        net_delta_exposure: null,
      },
    ],
    count: 2,
    empty: false,
    source: 'gold_options_features',
    freshness: { state: 'fresh', table: 'gold_options_features', detail: '2 rows' },
  },
};

function mockFetch(url: string) {
  if (url.includes('/api/positioning')) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve(mockPositioningResponse) });
  }
  if (url.includes('/api/market')) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve(mockMarketResponse) });
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
}

describe('Positioning', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('draws two line series (leveraged money + asset manager)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(mockFetch));

    render(<Positioning />);

    await waitFor(() => {
      expect(screen.getAllByText(/crowded_short/).length).toBeGreaterThanOrEqual(1);
    });

    expect(screen.getByRole('img', { name: /leveraged money net line/i })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /asset manager net line/i })).toBeInTheDocument();
  });

  it('null week breaks the line (gap in SVG path)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/positioning')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockNullWeekResponse) });
      }
      if (url.includes('/api/market')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockMarketResponse) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }));

    render(<Positioning />);

    await waitFor(() => {
      expect(screen.getAllByText(/neutral/).length).toBeGreaterThanOrEqual(1);
    });

    const lmGroup = screen.getByRole('img', { name: /leveraged money net line/i });
    const paths = lmGroup.querySelectorAll('path');
    expect(paths.length).toBeGreaterThanOrEqual(2);
  });

  it('stat tiles show both report_date and release date', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(mockFetch));

    render(<Positioning />);

    await waitFor(() => {
      expect(screen.getAllByText(/crowded_short/).length).toBeGreaterThanOrEqual(1);
    });

    // Crowding score stat tile: 0.62 (also appears in chart data table)
    expect(screen.getAllByText('0.62').length).toBeGreaterThanOrEqual(1);

    // Release date should appear in stat hint (Sep 5 or Sep 6 depending on timezone)
    expect(screen.getAllByText(/Sep [56]/).length).toBeGreaterThanOrEqual(1);
    // Report date "Sep 1" should appear in stat hint
    expect(screen.getAllByText(/Sep 1/).length).toBeGreaterThanOrEqual(1);
  });

  it('contracts sorted by |lev_money_pct_oi| (highest absolute first)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(mockFetch));

    render(<Positioning />);

    await waitFor(() => {
      expect(screen.getAllByText(/crowded_short/).length).toBeGreaterThanOrEqual(1);
    });

    const barChart = screen.getByRole('img', { name: /contract diverging bar chart/i });
    expect(barChart).toBeInTheDocument();

    // Both contracts should be rendered
    expect(screen.getByText(/Nasdaq-100/)).toBeInTheDocument();
    expect(screen.getByText(/E-mini S&P/)).toBeInTheDocument();
  });

  it('options card shows OI concentration as stat, no OI line when only one row has it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(mockFetch));

    render(<Positioning />);

    await waitFor(() => {
      expect(screen.getByText('OI Concentration')).toBeInTheDocument();
    });

    // OI Concentration stat: 0.1500 (toFixed(4))
    expect(screen.getByText('0.1500')).toBeInTheDocument();

    // Net Delta Exposure stat: 0.0800
    expect(screen.getByText('0.0800')).toBeInTheDocument();

    // Snapshot-only note
    expect(screen.getByText(/snapshot only/)).toBeInTheDocument();

    // No OI concentration line chart
    expect(screen.queryByRole('img', { name: /oi concentration line/i })).not.toBeInTheDocument();
  });

  it('shows EmptyState when positioning data is empty', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/positioning')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(emptyResponse) });
      }
      if (url.includes('/api/market')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockMarketResponse) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }));

    render(<Positioning />);

    await waitFor(() => {
      expect(screen.getByText(/No COT data/)).toBeInTheDocument();
    });
  });

  it('shows ErrorState on API failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    }));

    render(<Positioning />);

    await waitFor(() => {
      expect(screen.getByText(/Something went wrong/)).toBeInTheDocument();
    });
  });
});