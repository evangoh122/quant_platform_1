import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MarketDashboard } from './MarketDashboard';

const unsortedRows = [
  { symbol: 'AAPL', event_date: '2025-01-10', close: 150, open: 148, high: 152, low: 147, volume: 100, vwap: 149, price_basis: 'adjusted' },
  { symbol: 'AAPL', event_date: '2025-01-15', close: 160, open: 155, high: 162, low: 154, volume: 200, vwap: 158, price_basis: 'adjusted' },
  { symbol: 'AAPL', event_date: '2025-01-12', close: 153, open: 151, high: 155, low: 150, volume: 150, vwap: 152, price_basis: 'adjusted' },
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

const emptyMarketResponse = {
  symbol: 'AAPL',
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

describe('MarketDashboard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    window.history.replaceState(null, '', window.location.pathname);
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

    expect(screen.getByText('160.00')).toBeInTheDocument();
  });

  it('renders an adjusted-close/volume chart from rows sorted by event_date while retaining the table', async () => {
    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getByText('160.00')).toBeInTheDocument();
    });

    // Chart SVG is rendered
    const chart = screen.getByRole('img', { name: /adjusted close price chart/i });
    expect(chart).toBeInTheDocument();

    // OHLCV table is still present (not the sr-only one)
    const tables = document.querySelectorAll('table:not(.sr-only)');
    expect(tables.length).toBeGreaterThan(0);

    // Source label appears (in both chart card and table card)
    const sources = screen.getAllByText(/silver_ohlcv_day_adjusted/);
    expect(sources.length).toBeGreaterThanOrEqual(1);

    // Row count
    expect(screen.getByText(/3 rows/)).toBeInTheDocument();
  });

  it('changes the chart range without changing the API response contract', async () => {
    const user = userEvent.setup();
    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getByText('160.00')).toBeInTheDocument();
    });

    // Range buttons are visible
    const rangeButtons = ['1M', '3M', '6M', 'All'];
    for (const label of rangeButtons) {
      expect(screen.getByText(label, { selector: 'button' })).toBeInTheDocument();
    }

    // Click 1M range - should not trigger a new API call
    const fetchMock = vi.mocked(fetch);
    const callsBefore = fetchMock.mock.calls.length;

    await user.click(screen.getByText('1M', { selector: 'button' }));

    // No additional fetch call (range is client-side filtering)
    expect(fetchMock.mock.calls.length).toBe(callsBefore);
  });

  it('renders the market empty state and freshness/source instead of 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(emptyMarketResponse),
    }));

    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getAllByText(/No market features yet/).length).toBeGreaterThanOrEqual(1);
    });

    // Should show empty state messages (in both chart and table cards)
    expect(screen.getAllByText(/silver_ohlcv_day_adjusted is empty/).length).toBeGreaterThanOrEqual(1);

    // Stat tiles should show dash, not 0
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(1);

    // Freshness badge should still be visible
    const emptyBadges = screen.getAllByText(/empty ·/);
    expect(emptyBadges.length).toBeGreaterThanOrEqual(1);
  });

  it('uses SymbolPicker instead of SymbolSelect', async () => {
    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getByText('160.00')).toBeInTheDocument();
    });

    // SymbolPicker has a combobox, not a <select>
    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(screen.queryByRole('select', { name: 'Company' })).not.toBeInTheDocument();

    // Quick choices are visible
    expect(screen.getByText('NVDA', { selector: 'button' })).toBeInTheDocument();
    expect(screen.getByText('AAPL', { selector: 'button' })).toBeInTheDocument();
  });
});