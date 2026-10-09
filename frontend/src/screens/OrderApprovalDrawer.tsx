import { useState } from 'react';
import { api } from '../api/client';
import type { Order, OrderActionResult, Portfolio } from '../api/types';
import { useApi } from '../hooks/useApi';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { FreshnessBadge } from '../components/FreshnessBadge';

function timeAgo(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

const PENDING = 'PENDING_APPROVAL';

export function OrderApprovalDrawer() {
  const { data, loading, error, reload } = useApi<Portfolio>(() => api.portfolio());
  const [results, setResults] = useState<Record<string, OrderActionResult>>({});
  const [busy, setBusy] = useState<Record<string, boolean>>({});

  async function act(orderId: string, action: 'approve' | 'cancel') {
    setBusy((b) => ({ ...b, [orderId]: true }));
    try {
      const result = action === 'approve' ? await api.approveOrder(orderId) : await api.cancelOrder(orderId);
      setResults((r) => ({ ...r, [orderId]: result }));
      reload();
    } catch (e) {
      setResults((r) => ({ ...r, [orderId]: { order_id: orderId, status: 'ERROR', ok: false, broker_order_id: null, reason: e instanceof Error ? e.message : String(e), risk: null } }));
    } finally {
      setBusy((b) => ({ ...b, [orderId]: false }));
    }
  }

  const pending = (data?.orders.data ?? []).filter((o) => o.status === PENDING);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Order Approval Drawer</h1>
        {data && <FreshnessBadge freshness={data.orders.freshness} />}
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && pending.length === 0 && (
        <EmptyState
          title="No orders awaiting approval"
          detail="Orders with status PENDING_APPROVAL appear here for human review before placement."
        />
      )}
      {!loading && !error && pending.map((order) => (
        <ApprovalRow key={order.order_id} order={order} busy={!!busy[order.order_id]} result={results[order.order_id]} onApprove={() => void act(order.order_id, 'approve')} onReject={() => void act(order.order_id, 'cancel')} />
      ))}
    </div>
  );
}

function ApprovalRow({ order, busy, result, onApprove, onReject }: { order: Order; busy: boolean; result?: OrderActionResult; onApprove: () => void; onReject: () => void }) {
  return (
    <Card title={`${order.side} ${order.quantity} ${order.symbol}`} subtitle={order.order_id}>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm md:grid-cols-3">
        <div>
          <dt className="text-xs text-[var(--text-muted)]">Notional</dt>
          <dd>${order.notional.toFixed(2)}</dd>
        </div>
        <div>
          <dt className="text-xs text-[var(--text-muted)]">Order type</dt>
          <dd>{order.order_type}{order.limit_price != null ? ` @ ${order.limit_price}` : ''}</dd>
        </div>
        <div>
          <dt className="text-xs text-[var(--text-muted)]">Signal age</dt>
          <dd>{order.signal_id ? `${timeAgo(order.created_at)} (signal ${order.signal_id})` : 'no signal linked'}</dd>
        </div>
      </dl>

      {result && (
        <div className={`mt-3 rounded-md p-2 text-xs ${result.ok ? 'bg-success-fill text-[var(--on-success)]' : 'bg-warning-dim text-[var(--warning)]'}`}>
          <div className="font-semibold">Status: {result.status}</div>
          {result.reason && <div>{result.reason}</div>}
          {result.risk && <pre className="mt-1 whitespace-pre-wrap break-all text-[11px]">{JSON.stringify(result.risk, null, 2)}</pre>}
        </div>
      )}

      <div className="mt-3 flex gap-2">
        <button onClick={onApprove} disabled={busy} className="rounded-md bg-[var(--success-fill)] px-3 py-1.5 text-sm font-medium text-[var(--on-success)] hover:opacity-90 disabled:opacity-50">
          Approve & place
        </button>
        <button onClick={onReject} disabled={busy} className="rounded-md bg-[var(--danger-fill)] px-3 py-1.5 text-sm font-medium text-[var(--on-danger)] hover:opacity-90 disabled:opacity-50">
          Reject
        </button>
      </div>
    </Card>
  );
}
