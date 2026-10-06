import { useMemo } from 'react';
import { api } from '../api/client';
import type { Envelope, Signal } from '../api/types';
import { useApi } from '../hooks/useApi';
import { Card } from '../components/Card';
import { Table, type Column } from '../components/Table';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { FreshnessBadge } from '../components/FreshnessBadge';
import { ChartFrame } from '../components/charts';

const columns: Column<Signal>[] = [
  { key: 'symbol', header: 'Symbol', render: (r) => r.symbol },
  { key: 'direction', header: 'Direction', render: (r) => r.direction || '—' },
  {
    key: 'probability',
    header: 'Baseline model probability',
    render: (r) => (r.probability == null ? '—' : r.probability.toFixed(3)),
  },
  { key: 'horizon', header: 'Horizon', render: (r) => r.horizon || '—' },
  { key: 'ts', header: 'Prediction Time', render: (r) => r.prediction_ts || '—' },
  { key: 'model', header: 'Model', render: (r) => r.model_version || '—' },
  { key: 'status', header: 'Status', render: (r) => r.status || '—' },
];

interface SignalChartProps {
  signals: Signal[];
}

function SignalConvictionChart({ signals }: SignalChartProps) {
  const sorted = useMemo(
    () =>
      [...signals]
        .filter((s) => s.probability != null)
        .sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0)),
    [signals],
  );

  if (sorted.length === 0) {
    return <EmptyState title="No signals with probability" detail="No signals have a probability value to chart." />;
  }

  const barHeight = 24;
  const gap = 6;
  const labelWidth = 60;
  const chartWidth = 500;
  const barAreaWidth = chartWidth - labelWidth - 60;
  const totalHeight = sorted.length * (barHeight + gap) + 20;

  const maxProb = Math.max(...sorted.map((s) => s.probability ?? 0), 0.5);
  const probScale = (v: number) => (v / maxProb) * barAreaWidth;

  const tableData = {
    headers: ['Symbol', 'Direction', 'Baseline model probability', 'Model', 'Horizon'],
    rows: sorted.map((s) => [
      s.symbol,
      s.direction,
      s.probability?.toFixed(3) ?? '—',
      s.model_version,
      s.horizon,
    ]),
  };

  const captionParts = sorted.length > 0
    ? [sorted[0].model_version, sorted[0].horizon, sorted[0].prediction_ts].filter(Boolean)
    : [];

  return (
    <ChartFrame
      title="Baseline model probability"
      caption={captionParts.length > 0 ? captionParts.join(' · ') : undefined}
      legend={[
        { label: 'LONG', color: '#22c55e' },
        { label: 'SHORT', color: '#ef4444' },
      ]}
      tableData={tableData}
      width={chartWidth}
      height={totalHeight}
      ariaLabel="Signal conviction ranking chart"
    >
      {sorted.map((signal, i) => {
        const y = i * (barHeight + gap) + 10;
        const prob = signal.probability ?? 0;
        const barW = probScale(prob);
        const isLong = signal.direction?.toUpperCase() === 'LONG';
        const color = isLong ? '#22c55e' : '#ef4444';

        return (
          <g key={signal.signal_id}>
            <text
              x={labelWidth - 4}
              y={y + barHeight / 2 + 4}
              textAnchor="end"
              className="fill-slate-600 dark:fill-slate-300"
              style={{ fontSize: 10, fontWeight: 500 }}
            >
              {signal.symbol}
            </text>
            <rect
              x={labelWidth}
              y={y}
              width={Math.max(barW, 1)}
              height={barHeight}
              rx={3}
              fill={color}
              opacity={0.8}
            >
              <title>{`${signal.symbol}: ${(prob * 100).toFixed(1)}%`}</title>
            </rect>
            <text
              x={labelWidth + barW + 4}
              y={y + barHeight / 2 + 4}
              className="fill-slate-500 dark:fill-slate-400"
              style={{ fontSize: 10 }}
            >
              {(prob * 100).toFixed(1)}%
            </text>
          </g>
        );
      })}
    </ChartFrame>
  );
}

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
      <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-200">
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
        <>
          <Card
            title="Signal Conviction Ranking"
            subtitle="gold_trading_signals · sorted by baseline model probability"
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
              <SignalConvictionChart signals={data?.data ?? []} />
            )}
          </Card>

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
        </>
      )}
    </div>
  );
}