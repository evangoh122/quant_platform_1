import { useState } from 'react';
import { api } from '../api/client';
import type { MarketSnapshot } from '../api/types';
import { useApi } from '../hooks/useApi';
import { Card } from '../components/Card';
import { StatTile } from '../components/StatTile';
import { Table, type Column } from '../components/Table';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { FreshnessBadge } from '../components/FreshnessBadge';
import type { OHLCVFeature } from '../api/types';

const ohlcvColumns: Column<OHLCVFeature>[] = [
  { key: 'ts', header: 'Date', render: (r) => r.event_date || '—' },
  { key: 'open', header: 'Open', render: (r) => (r.open ?? '—').toString() },
  { key: 'high', header: 'High', render: (r) => (r.high ?? '—').toString() },
  { key: 'low', header: 'Low', render: (r) => (r.low ?? '—').toString() },
  { key: 'close', header: 'Close', render: (r) => (r.close ?? '—').toString() },
  { key: 'volume', header: 'Volume', render: (r) => (r.volume ?? '—').toString() },
  { key: 'vwap', header: 'VWAP', render: (r) => (r.vwap ?? '—').toString() },
];

export function MarketDashboard() {
  const [input, setInput] = useState('NVDA');
  const [symbol, setSymbol] = useState('NVDA');
  const { data, loading, error, reload } = useApi<MarketSnapshot>(
    () => api.market(symbol),
    [symbol],
  );

  const latest = data?.ohlcv.data.reduce((best, r) =>
    r.event_date > (best?.event_date ?? '') ? r : best,
    data?.ohlcv.data[0],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Market Dashboard</h1>
        <div className="flex items-center gap-2">
          {data && (
            <FreshnessBadge freshness={data.ohlcv.freshness} />
          )}
        </div>
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
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatTile label="Latest Close" value={latest?.close?.toFixed(2) ?? '—'} hint={symbol} />
            <StatTile label="Volume" value={latest?.volume?.toLocaleString() ?? '—'} />
            <StatTile label="ATM IV" value={data?.options.data[0]?.iv_atm?.toFixed(4) ?? '—'} />
            <StatTile label="Skew" value={data?.options.data[0]?.iv_skew?.toFixed(4) ?? '—'} />
          </div>

          <Card title="OHLCV Features" subtitle="silver_ohlcv_day_adjusted" actions={<FreshnessBadge freshness={data ? data.ohlcv.freshness : { state: 'empty', table: '', detail: '' }} />}>
            {data && data.ohlcv.empty ? (
              <EmptyState
                title="No market features yet"
                detail={`silver_ohlcv_day_adjusted is empty for ${symbol} — features appear once the silver→gold pipeline has run.`}
              />
            ) : (
              <Table columns={ohlcvColumns} rows={data?.ohlcv.data ?? []} rowKey={(r) => r.event_date || r.symbol} />
            )}
          </Card>
        </>
      )}
    </div>
  );
}
