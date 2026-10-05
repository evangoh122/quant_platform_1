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
  { key: 'realized', header: 'Realized P&L', render: (r) => r.realized_pnl.toFixed(2) },
  { key: 'unrealized', header: 'Unrealized P&L', render: (r) => r.unrealized_pnl.toFixed(2) },
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

  const realized = (data?.positions.data ?? []).reduce((sum, p) => sum + p.realized_pnl, 0);
  const unrealized = (data?.positions.data ?? []).reduce((sum, p) => sum + p.unrealized_pnl, 0);

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
            <StatTile label="Total P&L" value={(realized + unrealized).toFixed(2)} hint={`realized ${realized.toFixed(2)}`} />
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
