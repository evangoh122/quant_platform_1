import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { OrderApprovalDrawer } from './OrderApprovalDrawer';

const pendingPortfolio = {
  positions: {
    data: [],
    count: 0,
    empty: true,
    source: 'positions',
    freshness: { state: 'empty', table: 'positions', detail: '0 rows' },
  },
  orders: {
    data: [
      {
        order_id: 'ord-1',
        symbol: 'AAPL',
        side: 'BUY',
        quantity: 1,
        notional: null,
        order_type: 'MARKET',
        limit_price: null,
        status: 'PENDING_APPROVAL',
        signal_id: null,
        idempotency_key: 'key-1',
        created_at: '2026-10-07T00:00:00Z',
      },
    ],
    count: 1,
    empty: false,
    source: 'orders',
    freshness: { state: 'fresh', table: 'orders', detail: '1 row' },
  },
};

describe('OrderApprovalDrawer', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders an em dash instead of throwing when notional is null', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(pendingPortfolio),
      }),
    );

    render(<OrderApprovalDrawer />);

    await waitFor(() => {
      expect(screen.getByText('BUY 1 AAPL')).toBeInTheDocument();
    });
    expect(screen.getByText('$\u2014')).toBeInTheDocument();
  });
});
