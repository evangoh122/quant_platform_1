import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PaperPortfolio } from './PaperPortfolio';

const mockPortfolioWithNullPnl = {
  positions: {
    data: [
      {
        account_id: 'default',
        symbol: 'AAPL',
        quantity: 100,
        avg_cost: 150.0,
        market_price: null,
        realized_pnl: null,
        unrealized_pnl: null,
        updated_at: '2026-10-07',
      },
      {
        account_id: 'default',
        symbol: 'MSFT',
        quantity: 50,
        avg_cost: 300.0,
        market_price: 310.0,
        realized_pnl: 500.0,
        unrealized_pnl: -200.0,
        updated_at: '2026-10-07',
      },
    ],
    count: 2,
    empty: false,
    source: 'positions',
    freshness: { state: 'fresh', table: 'positions', detail: '2 rows' },
  },
  orders: {
    data: [],
    count: 0,
    empty: true,
    source: 'orders',
    freshness: { state: 'empty', table: 'orders', detail: '0 rows' },
  },
};

function mockFetch(data: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(data),
  }));
}

describe('PaperPortfolio', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders em dash for null P&L values', async () => {
    mockFetch(mockPortfolioWithNullPnl);
    render(<PaperPortfolio />);

    await waitFor(() => {
      expect(screen.getByText('IBKR Paper Portfolio')).toBeInTheDocument();
    });

    // AAPL has null market_price, null realized_pnl, null unrealized_pnl = 3 dashes
    // MSFT has non-null values for all = 0 dashes
    const emDashes = screen.getAllByText('\u2014');
    expect(emDashes.length).toBeGreaterThanOrEqual(3);
  });

  it('does not render $0.00 for null P&L cells', async () => {
    mockFetch(mockPortfolioWithNullPnl);
    render(<PaperPortfolio />);

    await waitFor(() => {
      expect(screen.getByText('IBKR Paper Portfolio')).toBeInTheDocument();
    });

    // Total P&L should be 300.00 (realized 500, unrealized -200), not 0.00.
    // AAPL's P&L cells are em dashes, not "0.00".
    const allText = document.body.textContent || '';
    const zeroZeroMatches = allText.match(/\b0\.00\b/g) || [];
    expect(zeroZeroMatches.length).toBe(0);
  });

  it('sums realized and unrealized independently; shows unpriced note', async () => {
    // Codex's case: realized=50 with null unrealized must count toward realized.
    // realized = 500 (MSFT only; AAPL excluded — null realized)
    // unrealized = -200 (MSFT only; AAPL excluded — null unrealized)
    // total = 300.00
    // 1 position has null unrealized → unpriced note
    mockFetch(mockPortfolioWithNullPnl);
    render(<PaperPortfolio />);

    await waitFor(() => {
      expect(screen.getByText('IBKR Paper Portfolio')).toBeInTheDocument();
    });

    // Total P&L = 500 + (-200) = 300.00
    const allThreeHundred = screen.getAllByText('300.00');
    expect(allThreeHundred.length).toBeGreaterThanOrEqual(1);

    // "unpriced" note with count 1
    expect(screen.getByText(/1 unpriced/)).toBeInTheDocument();
  });

  it('shows em dash for Total P&L when all P&L values are null', async () => {
    const allNull = {
      ...mockPortfolioWithNullPnl,
      positions: {
        ...mockPortfolioWithNullPnl.positions,
        data: [
          {
            account_id: 'default',
            symbol: 'AAPL',
            quantity: 100,
            avg_cost: 150.0,
            market_price: null,
            realized_pnl: null,
            unrealized_pnl: null,
            updated_at: '2026-10-07',
          },
          {
            account_id: 'default',
            symbol: 'MSFT',
            quantity: 50,
            avg_cost: 300.0,
            market_price: null,
            realized_pnl: null,
            unrealized_pnl: null,
            updated_at: '2026-10-07',
          },
        ],
      },
    };
    mockFetch(allNull);
    render(<PaperPortfolio />);

    await waitFor(() => {
      expect(screen.getByText('IBKR Paper Portfolio')).toBeInTheDocument();
    });

    // Total P&L StatTile value should be "—" (em dash)
    // The em dash appears in table cells AND in the StatTile value.
    // AAPL: 3 null cells (market, realized, unrealized) + MSFT: 3 null cells = 6 table dashes
    // + 1 StatTile Total P&L value dash = 7 total
    const emDashes = screen.getAllByText('\u2014');
    expect(emDashes.length).toBeGreaterThanOrEqual(7);

    // No "0.00" anywhere — the total must not coerce null to 0.
    const allText = document.body.textContent || '';
    expect(allText).not.toMatch(/\b0\.00\b/);

    // No "unpriced" note when total is completely unknown.
    expect(screen.queryByText(/unpriced/)).not.toBeInTheDocument();
  });

  it('shows correct totals when all positions are fully priced', async () => {
    const allPriced = {
      ...mockPortfolioWithNullPnl,
      positions: {
        ...mockPortfolioWithNullPnl.positions,
        data: [
          {
            account_id: 'default',
            symbol: 'AAPL',
            quantity: 100,
            avg_cost: 150.0,
            market_price: 155.0,
            realized_pnl: 500.0,
            unrealized_pnl: -200.0,
            updated_at: '2026-10-07',
          },
          {
            account_id: 'default',
            symbol: 'GOOG',
            quantity: 200,
            avg_cost: 100.0,
            market_price: 110.0,
            realized_pnl: 100.0,
            unrealized_pnl: 0.0,
            updated_at: '2026-10-07',
          },
        ],
      },
    };
    // Hand-computed:
    // realized = 500 + 100 = 600
    // unrealized = -200 + 0 = -200
    // total = 600 + (-200) = 400
    mockFetch(allPriced);
    render(<PaperPortfolio />);

    await waitFor(() => {
      expect(screen.getByText('IBKR Paper Portfolio')).toBeInTheDocument();
    });

    expect(screen.getByText('400.00')).toBeInTheDocument();

    // No unpriced note — all positions have both values.
    expect(screen.queryByText(/unpriced/)).not.toBeInTheDocument();
  });

  it('handles empty positions', async () => {
    const empty = {
      ...mockPortfolioWithNullPnl,
      positions: {
        ...mockPortfolioWithNullPnl.positions,
        data: [],
        count: 0,
        empty: true,
      },
    };
    mockFetch(empty);
    render(<PaperPortfolio />);

    await waitFor(() => {
      expect(screen.getByText('IBKR Paper Portfolio')).toBeInTheDocument();
    });

    // Empty positions → EmptyState message.
    expect(screen.getByText('No positions')).toBeInTheDocument();
  });

  it('counts unpriced realized independently of unpriced unrealized', async () => {
    // Positions: AAPL realized=50/unrealized=null, GOOG realized=null/unrealized=300
    // realized = 50 (AAPL only; GOOG has null realized)
    // unrealized = 300 (GOOG only; AAPL has null unrealized)
    // unpricedUnrealized = 1 (AAPL), unpricedRealized = 1 (GOOG)
    // total = 350
    const mixed = {
      ...mockPortfolioWithNullPnl,
      positions: {
        ...mockPortfolioWithNullPnl.positions,
        data: [
          {
            account_id: 'default',
            symbol: 'AAPL',
            quantity: 100,
            avg_cost: 150.0,
            market_price: 155.0,
            realized_pnl: 50.0,
            unrealized_pnl: null,
            updated_at: '2026-10-07',
          },
          {
            account_id: 'default',
            symbol: 'GOOG',
            quantity: 200,
            avg_cost: 100.0,
            market_price: null,
            realized_pnl: null,
            unrealized_pnl: 300.0,
            updated_at: '2026-10-07',
          },
        ],
      },
    };
    mockFetch(mixed);
    render(<PaperPortfolio />);

    await waitFor(() => {
      expect(screen.getByText('IBKR Paper Portfolio')).toBeInTheDocument();
    });

    // Total P&L = 50 + 300 = 350
    expect(screen.getByText('350.00')).toBeInTheDocument();

    // Hint: "realized 50.00 (1 unpriced)" — unpricedUnrealized=1
    expect(screen.getByText(/realized 50\.00/)).toBeInTheDocument();
    expect(screen.getByText(/1 unpriced/)).toBeInTheDocument();
  });
});