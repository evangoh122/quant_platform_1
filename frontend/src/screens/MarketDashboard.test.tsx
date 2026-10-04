import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MarketDashboard } from './MarketDashboard';

const unsortedRows = [
  { symbol: 'AAPL', event_date: '2025-01-10', close: 150, open: 148, high: 152, low: 147, volume: 100, vwap: 149 },
  { symbol: 'AAPL', event_date: '2025-01-15', close: 160, open: 155, high: 162, low: 154, volume: 200, vwap: 158 },
  { symbol: 'AAPL', event_date: '2025-01-12', close: 153, open: 151, high: 155, low: 150, volume: 150, vwap: 152 },
];

const mockMarketResponse = {
  symbol: 'AAPL',
  ohlcv: {
    data: unsortedRows,
    count: 3,
    empty: false,
    source: 'silver_ohlcv_day_adjusted',
    freshness: { state: 'fresh', table: 'silver_ohlcv_day_adjusted', detail: '3 rows' },
  },
  options: {
    data: [],
    count: 0,
    empty: true,
    source: 'gold_options_features',
    freshness: { state: 'empty', table: 'gold_options_features', detail: '0 rows' },
  },
};

describe('MarketDashboard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockMarketResponse),
    }));
  });

  it('picks MAX event_date from unsorted rows', async () => {
    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getByText('160.00')).toBeInTheDocument();
    });

    // The latest close should be from 2025-01-15 (max date), not 2025-01-10 (first row)
    expect(screen.getByText('160.00')).toBeInTheDocument();
  });
});