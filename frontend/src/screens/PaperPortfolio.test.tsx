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

describe('PaperPortfolio', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders em dash for null P&L values', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockPortfolioWithNullPnl),
    }));

    render(<PaperPortfolio />);

    await waitFor(() => {
      expect(screen.getByText('IBKR Paper Portfolio')).toBeInTheDocument();
    });

    // The em dash should appear for null realized_pnl and unrealized_pnl of AAPL
    const emDashes = screen.getAllByText('—');
    // AAPL has null market_price, null realized_pnl, null unrealized_pnl = 3 dashes
    // MSFT has non-null values for all
    expect(emDashes.length).toBeGreaterThanOrEqual(3);
  });

  it('does not render $0.00 for null P&L cells', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockPortfolioWithNullPnl),
    }));

    render(<PaperPortfolio />);

    await waitFor(() => {
      expect(screen.getByText('IBKR Paper Portfolio')).toBeInTheDocument();
    });

    // $0.00 should NOT appear for the null P&L position
    // MSFT's realized (500.00) and unrealized (-200.00) are fine
    // AAPL's realized and unrealized should be "—", not "0.00"
    const allText = document.body.textContent || '';
    // Count occurrences of "0.00" — should only come from non-P&L fields if any
    // The key assertion: "0.00" should not appear as a P&L value for AAPL
    // Since AAPL's quantity (100) and avg_cost (150.00→"150.00") don't produce "0.00",
    // any "0.00" would be a bug from null coercion
    const zeroZeroMatches = allText.match(/\b0\.00\b/g) || [];
    // "0.00" should not appear at all since no field legitimately has that value
    expect(zeroZeroMatches.length).toBe(0);
  });

  it('excludes null P&L from totals and shows unpriced note', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockPortfolioWithNullPnl),
    }));

    render(<PaperPortfolio />);

    await waitFor(() => {
      expect(screen.getByText('IBKR Paper Portfolio')).toBeInTheDocument();
    });

    // Total P&L should be based only on MSFT: realized=500, unrealized=-200, total=300
    // AAPL is excluded because its P&L is null
    // "300.00" appears in both the StatTile and MSFT's avg_cost column
    const allThreeHundred = screen.getAllByText('300.00');
    expect(allThreeHundred.length).toBeGreaterThanOrEqual(2);

    // "unpriced" note should appear indicating 1 position was excluded
    expect(screen.getByText(/1 unpriced/)).toBeInTheDocument();
  });
});
