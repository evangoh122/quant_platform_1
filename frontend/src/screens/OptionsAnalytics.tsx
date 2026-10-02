import { useState } from 'react';
import { api } from '../api/client';
import type { MarketSnapshot, OptionsFeature } from '../api/types';
import { useApi } from '../hooks/useApi';
import { Card } from '../components/Card';
import { Table, type Column } from '../components/Table';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { FreshnessBadge } from '../components/FreshnessBadge';

const columns: Column<OptionsFeature>[] = [
  { key: 'expiry', header: 'Expiry', render: (r) => r.expiry || '—' },
  { key: 'iv', header: 'ATM IV', render: (r) => (r.atm_iv == null ? '—' : r.atm_iv.toFixed(4)) },
  { key: 'skew', header: 'Skew', render: (r) => (r.skew == null ? '—' : r.skew.toFixed(4)) },
  {
    key: 'pc',
    header: 'Put/Call Ratio',
    render: (r) => (r.put_call_ratio == null ? '—' : r.put_call_ratio.toFixed(4)),
  },
  {
    key: 'vol',
    header: 'Volume Anomaly',
    render: (r) => (r.volume_anomaly == null ? '—' : r.volume_anomaly.toFixed(4)),
  },
];

export function OptionsAnalytics() {
  const [input, setInput] = useState('NVDA');
  const [symbol, setSymbol] = useState('NVDA');
  const { data, loading, error, reload } = useApi<MarketSnapshot>(
    () => api.market(symbol),
    [symbol],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Options Analytics</h1>
        {data && <FreshnessBadge freshness={data.options.freshness} />}
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const s = input.trim().toUpperCase();
          if (s) setSymbol(s);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          placeholder="Symbol (e.g. NVDA)"
        />
        <button
          type="submit"
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-slate-100 dark:text-slate-900"
        >
          Search
        </button>
      </form>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && (
        <Card title="Options Chain Metrics" subtitle="gold_options_features · IV / skew / unusual volume">
          {data && data.options.empty ? (
            <EmptyState
              title="No options features yet"
              detail={`gold_options_features is empty for ${symbol} — IV, skew and volume anomalies appear after the options gold transform runs.`}
            />
          ) : (
            <Table columns={columns} rows={data?.options.data ?? []} rowKey={(r) => `${r.symbol}-${r.expiry}-${r.feature_ts}`} />
          )}
        </Card>
      )}
    </div>
  );
}
