import { api } from '../api/client';
import type { Order, Portfolio, Position } from '../api/types';
import { useApi } from '../hooks/useApi';
import { Card } from '../components/Card';
import { StatTile } from '../components/StatTile';
import { Table, type Column } from '../components/Table';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { FreshnessBadge } from '../components/FreshnessBadge';

const positionColumns: Column<Position>[] = [
  { key: 'symbol', header: 'Symbol', render: (r) => r.symbol },
  { key: 'qty', header: 'Quantity', render: (r) => r.quantity.toString() },
  { key: 'avg', header: 'Avg Cost', render: (r) => r.avg_cost.toFixed(2) },
  { key: 'mkt', header: 'Market', render: (r) => (r.market_price == null ? '—' : r.market_price.toFixed(2)) },
  { key: 'realized', header: 'Realized P&L', render: (r) => (r.realized_pnl == null ? '—' : r.realized_pnl.toFixed(2)) },
  { key: 'unrealized', header: 'Unrealized P&L', render: (r) => (r.unrealized_pnl == null ? '—' : r.unrealized_pnl.toFixed(2)) },
];

const orderColumns: Column<Order>[] = [
  { key: 'id', header: 'Order', render: (r) => r.order_id },
  { key: 'symbol', header: 'Symbol', render: (r) => r.symbol },
  { key: 'side', header: 'Side', render: (r) => r.side },
  { key: 'qty', header: 'Qty', render: (r) => r.quantity.toString() },
  { key: 'notional', header: 'Notional', render: (r) => r.notional.toFixed(2) },
  { key: 'status', header: 'Status', render: (r) => r.status },
];

export function PaperPortfolio() {
  const { data, loading, error, reload } = useApi<Portfolio>(() => api.portfolio());

  const positions = data?.positions.data ?? [];
  const realized = positions.reduce((sum, p) => (p.realized_pnl != null ? sum + p.realized_pnl : sum), 0);
  const unrealized = positions.reduce((sum, p) => (p.unrealized_pnl != null ? sum + p.unrealized_pnl : sum), 0);
  const unpricedUnrealized = positions.filter((p) => p.unrealized_pnl == null).length;
  const unpricedRealized = positions.filter((p) => p.realized_pnl == null).length;
  const hasRealized = positions.some((p) => p.realized_pnl != null);
  const hasUnrealized = positions.some((p) => p.unrealized_pnl != null);
  const totalPnlKnown = hasRealized || hasUnrealized;
  const totalPnl = realized + unrealized;

  return (
    <div data-tour="lakebase-write" className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">IBKR Paper Portfolio</h1>
        {data && <FreshnessBadge freshness={data.positions.freshness} />}
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <StatTile label="Positions" value={(data?.positions.data.length ?? 0).toString()} />
            <StatTile label="Open Orders" value={(data?.orders.data.length ?? 0).toString()} />
            <StatTile
              label="Total P&L"
              value={totalPnlKnown ? totalPnl.toFixed(2) : '\u2014'}
              hint={
                !totalPnlKnown
                  ? undefined
                  : unpricedUnrealized > 0 || unpricedRealized > 0
                    ? `realized ${realized.toFixed(2)}${unpricedUnrealized > 0 ? ` (${unpricedUnrealized} unpriced)` : ''}`
                    : undefined
              }
            />
          </div>

          <Card title="Positions" subtitle="Lakebase · positions">
            {data && data.positions.empty ? (
              <EmptyState title="No positions" detail="positions is empty — fills from the paper-trading bridge will appear here." />
            ) : (
              <Table columns={positionColumns} rows={data?.positions.data ?? []} rowKey={(r) => `${r.account_id}-${r.symbol}`} />
            )}
          </Card>

          <Card title="Open Orders" subtitle="Lakebase · orders">
            {data && data.orders.empty ? (
              <EmptyState title="No open orders" detail="orders is empty — order intents appear here once created from the AI agent or order drawer." />
            ) : (
              <Table columns={orderColumns} rows={data?.orders.data ?? []} rowKey={(r) => r.order_id} />
            )}
          </Card>
        </>
      )}
    </div>
  );
}
