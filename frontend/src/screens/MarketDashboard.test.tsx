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

    // Table rows contain actual data (not empty)
    const table = tables[0];
    const dataRows = table.querySelectorAll('tbody tr');
    expect(dataRows.length).toBe(3);
    expect(dataRows[0].textContent).toContain('2025-01-10');
    expect(dataRows[0].textContent).toContain('150');
    expect(dataRows[1].textContent).toContain('2025-01-12');
    expect(dataRows[2].textContent).toContain('2025-01-15');
    expect(dataRows[2].textContent).toContain('160');

    // Source label appears (in both chart card and table card)
    const sources = screen.getAllByText(/silver_ohlcv_day_adjusted/);
    expect(sources.length).toBeGreaterThanOrEqual(1);

    // Row count
    expect(screen.getByText(/3 rows/)).toBeInTheDocument();
  });

  it('sorts chart rows by event_date ascending', async () => {
    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getByText('160.00')).toBeInTheDocument();
    });

    // The accessible fallback table (sr-only) should have rows in sorted order
    const srTable = document.querySelector('table.sr-only');
    expect(srTable).toBeTruthy();
    const srRows = srTable!.querySelectorAll('tbody tr');
    expect(srRows.length).toBe(3);
    // Sorted: Jan 10, Jan 12, Jan 15
    expect(srRows[0].textContent).toContain('2025-01-10');
    expect(srRows[1].textContent).toContain('2025-01-12');
    expect(srRows[2].textContent).toContain('2025-01-15');
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

  it('shows no coverage indicator for empty envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(emptyMarketResponse),
    }));

    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getAllByText(/No market features yet/).length).toBeGreaterThanOrEqual(1);
    });

    // No "Has data" badge should appear when envelope is empty
    expect(screen.queryByText('Has data')).not.toBeInTheDocument();
  });

  it('drops null close/volume points instead of rendering zero', async () => {
    const withNulls = {
      symbol: 'AAPL',
      ohlcv: {
        data: [
          { symbol: 'AAPL', event_date: '2025-01-10', close: 150, open: 148, high: 152, low: 147, volume: 100, vwap: 149, price_basis: 'adjusted' },
          { symbol: 'AAPL', event_date: '2025-01-11', close: null, open: 148, high: 152, low: 147, volume: null, vwap: 149, price_basis: 'adjusted' },
          { symbol: 'AAPL', event_date: '2025-01-12', close: 153, open: 151, high: 155, low: 150, volume: 150, vwap: 152, price_basis: 'adjusted' },
        ],
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

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(withNulls),
    }));

    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getByText('153.00')).toBeInTheDocument();
    });

    // Chart should be rendered
    const chart = screen.getByRole('img', { name: /adjusted close price chart/i });
    expect(chart).toBeInTheDocument();

    // Should show missing points message
    expect(screen.getByText(/1 missing point/)).toBeInTheDocument();

    // Volume bars: only 2 non-null volume rows should produce bars (not 3 with 0)
    // The SVG should have exactly 2 volume rect elements
    const rects = chart.querySelectorAll('rect');
    expect(rects.length).toBe(2);
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

  it('anchors 1M range to latest event_date, not Date.now()', async () => {
    const historicalRows = [
      { symbol: 'AAPL', event_date: '2026-07-15', close: 100, open: 99, high: 101, low: 98, volume: 50, vwap: 100, price_basis: 'adjusted' },
      { symbol: 'AAPL', event_date: '2026-08-01', close: 110, open: 108, high: 112, low: 107, volume: 60, vwap: 109, price_basis: 'adjusted' },
      { symbol: 'AAPL', event_date: '2026-08-15', close: 120, open: 118, high: 122, low: 117, volume: 70, vwap: 119, price_basis: 'adjusted' },
      { symbol: 'AAPL', event_date: '2026-09-02', close: 130, open: 128, high: 132, low: 127, volume: 80, vwap: 129, price_basis: 'adjusted' },
    ];

    const response = {
      symbol: 'AAPL',
      ohlcv: {
        data: historicalRows,
        count: 4,
        empty: false,
        source: 'silver_ohlcv_day_adjusted',
        freshness: { state: 'fresh', table: 'silver_ohlcv_day_adjusted', detail: '4 rows' },
      },
      options: {
        data: [],
        count: 0,
        empty: true,
        source: 'gold_options_features',
        freshness: { state: 'empty', table: 'gold_options_features', detail: '0 rows' },
      },
    };

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(response),
    }));

    // Mock Date.now() to return 2026-10-06 so the test is deterministic
    const realDateNow = Date.now;
    Date.now = () => new Date('2026-10-06T12:00:00Z').getTime();

    const user = userEvent.setup();
    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getByText('130.00')).toBeInTheDocument();
    });

    // All data should be visible in "All" range
    const chart = screen.getByRole('img', { name: /adjusted close price chart/i });
    expect(chart).toBeInTheDocument();

    // Click 1M — anchored to latest event_date 2026-09-02, so cutoff = 2026-08-03
    // Should show Aug 15 and Sep 2 points (>= 2026-08-03), NOT Jul 15
    await user.click(screen.getByText('1M', { selector: 'button' }));

    // The accessible fallback table should show the filtered rows
    const srTable = document.querySelector('table.sr-only');
    expect(srTable).toBeTruthy();
    const srRows = srTable!.querySelectorAll('tbody tr');

    // 1M from 2026-09-02 → cutoff 2026-08-03 → Aug 15 and Sep 2 = 2 rows
    expect(srRows.length).toBe(2);
    expect(srRows[0].textContent).toContain('2026-08-15');
    expect(srRows[1].textContent).toContain('2026-09-02');

    // Restore Date.now
    Date.now = realDateNow;
  });

  it('skips fetch and shows prompt when symbol is cleared', async () => {
    const user = userEvent.setup();
    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getByText('160.00')).toBeInTheDocument();
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

  it('keeps the range controls when the selected range has no finite closes, so the user can switch back', async () => {
    const recentNullClose = {
      symbol: 'AAPL',
      ohlcv: {
        data: [
          { symbol: 'AAPL', event_date: '2025-01-10', close: 150, open: 148, high: 152, low: 147, volume: 100, vwap: 149, price_basis: 'adjusted' },
          { symbol: 'AAPL', event_date: '2025-01-11', close: 151, open: 148, high: 152, low: 147, volume: 120, vwap: 149, price_basis: 'adjusted' },
          { symbol: 'AAPL', event_date: '2025-06-01', close: null, open: 151, high: 155, low: 150, volume: 150, vwap: 152, price_basis: 'adjusted' },
          { symbol: 'AAPL', event_date: '2025-06-02', close: null, open: 151, high: 155, low: 150, volume: 150, vwap: 152, price_basis: 'adjusted' },
        ],
        count: 4,
        empty: false,
        source: 'silver_ohlcv_day_adjusted',
        freshness: { state: 'fresh', table: 'silver_ohlcv_day_adjusted', detail: '4 rows' },
      },
      options: {
        data: [],
        count: 0,
        empty: true,
        source: 'gold_options_features',
        freshness: { state: 'empty', table: 'gold_options_features', detail: '0 rows' },
      },
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(recentNullClose) }));
    const user = userEvent.setup();
    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getByRole('img', { name: /adjusted close price chart/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: '1M' }));
    expect(screen.getByText(/No finite close values/)).toBeInTheDocument();
    // The range selector is still there and switching back restores the chart.
    await user.click(screen.getByRole('button', { name: 'All' }));
    expect(screen.getByRole('img', { name: /adjusted close price chart/i })).toBeInTheDocument();
  });

  it('renders EmptyState when all close values are null and no svg axis labels', async () => {
    const allNullClose = {
      symbol: 'AAPL',
      ohlcv: {
        data: [
          { symbol: 'AAPL', event_date: '2025-01-10', close: null, open: 148, high: 152, low: 147, volume: 100, vwap: 149, price_basis: 'adjusted' },
          { symbol: 'AAPL', event_date: '2025-01-11', close: null, open: 148, high: 152, low: 147, volume: null, vwap: 149, price_basis: 'adjusted' },
          { symbol: 'AAPL', event_date: '2025-01-12', close: null, open: 151, high: 155, low: 150, volume: 150, vwap: 152, price_basis: 'adjusted' },
        ],
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

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(allNullClose),
    }));

    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getByText(/No finite close values/)).toBeInTheDocument();
    });

    // No chart SVG should be rendered
    expect(screen.queryByRole('img', { name: /adjusted close price chart/i })).not.toBeInTheDocument();

    // No axis labels like 0.0, 0.5, 1.0 should appear
    expect(screen.queryByText('0.0')).not.toBeInTheDocument();
    expect(screen.queryByText('1.0')).not.toBeInTheDocument();
  });

  it('fetches again when a symbol is picked after clearing', async () => {
    const user = userEvent.setup();
    render(<MarketDashboard />);

    await waitFor(() => {
      expect(screen.getByText('160.00')).toBeInTheDocument();
    });

    // Clear the symbol
    const clearBtn = screen.getByLabelText('Clear');
    await user.click(clearBtn);

    await waitFor(() => {
      expect(screen.getByText(/Select a symbol/)).toBeInTheDocument();
    });

    // Pick NVDA from quick choices
    await user.click(screen.getByText('NVDA', { selector: 'button' }));

    // Should trigger a fetch for NVDA
    await waitFor(() => {
      const fetchMock = vi.mocked(fetch);
      const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
      expect(String(lastCall[0])).toContain('/api/market/NVDA');
    });
  });
});