import { api } from '../api/client';
import type { Envelope, Signal } from '../api/types';
import { useApi } from '../hooks/useApi';
import { Card } from '../components/Card';
import { Table, type Column } from '../components/Table';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { FreshnessBadge } from '../components/FreshnessBadge';

const columns: Column<Signal>[] = [
  { key: 'symbol', header: 'Symbol', render: (r) => r.symbol },
  { key: 'direction', header: 'Direction', render: (r) => r.direction || '—' },
  {
    key: 'probability',
    header: 'Probability',
    render: (r) => (r.probability == null ? '—' : r.probability.toFixed(3)),
  },
  { key: 'horizon', header: 'Horizon', render: (r) => r.horizon || '—' },
  { key: 'ts', header: 'Prediction Time', render: (r) => r.prediction_ts || '—' },
  { key: 'model', header: 'Model', render: (r) => r.model_version || '—' },
  { key: 'status', header: 'Status', render: (r) => r.status || '—' },
];

export function SignalExplorer() {
  const { data, loading, error, reload } = useApi<Envelope<Signal>>(() => api.signals());

  const isNoSignalsPublished =
    data?.freshness?.detail === 'no_signals_published' ||
    (data?.freshness?.state === 'empty' && data?.freshness?.table === 'gold_trading_signals');

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Signal Explorer</h1>
        {data && <FreshnessBadge freshness={data.freshness} />}
      </div>
      <div className="rounded-md border border-[var(--info)]/20 bg-[var(--info)]/8 px-3 py-2 text-xs text-[var(--info)]">
        <strong>Baseline demonstration</strong>
        {data?.data && data.data.length > 0 && (
          <>
            {': '}
            {Array.from(new Set(data.data.map((r) => r.model_version).filter(Boolean))).join(', ')}
            {data.data[0]?.horizon && ` · ${data.data[0].horizon}`}
          </>
        )}
        {' '}&mdash; no validated trading edge claimed.
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && (
        <Card
          title="Ranked Trading Signals"
          subtitle="gold_trading_signals · ranked by prediction time"
        >
          {data && data.empty ? (
            <EmptyState
              title={isNoSignalsPublished ? 'No signals published yet' : 'No signals yet'}
              detail={
                isNoSignalsPublished
                  ? 'gold_trading_signals is empty — no signals have been published by the model inference pipeline yet.'
                  : 'gold_trading_signals is empty — signals appear once the model inference pipeline produces predictions.'
              }
            />
          ) : (
            <Table columns={columns} rows={data?.data ?? []} rowKey={(r) => r.signal_id} />
          )}
        </Card>
      )}
    </div>
  );
}
