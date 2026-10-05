import { useState } from 'react';
import { SymbolSelect } from '../components/SymbolSelect';
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
  { key: 'iv_atm', header: 'ATM IV', render: (r) => (r.iv_atm == null ? '—' : r.iv_atm.toFixed(4)) },
  { key: 'iv_skew', header: 'IV Skew', render: (r) => (r.iv_skew == null ? '—' : r.iv_skew.toFixed(4)) },
  {
    key: 'pc',
    header: 'Put/Call Ratio',
    render: (r) => (r.put_call_ratio == null ? '—' : r.put_call_ratio.toFixed(4)),
  },
  {
    key: 'vol_anom',
    header: 'Volume Anomaly Z',
    render: (r) => (r.volume_anomaly_zscore == null ? '—' : r.volume_anomaly_zscore.toFixed(2)),
  },
  {
    key: 'put_vol',
    header: 'Put Volume',
    render: (r) => (r.put_volume == null ? '—' : r.put_volume.toLocaleString()),
  },
  {
    key: 'call_vol',
    header: 'Call Volume',
    render: (r) => (r.call_volume == null ? '—' : r.call_volume.toLocaleString()),
  },
];

export function OptionsAnalytics() {
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

      <div className="flex items-center gap-2">
        <label className="text-sm text-slate-600 dark:text-slate-400">Company</label>
        <SymbolSelect value={symbol} onChange={setSymbol} list="options" />
      </div>

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
            <Table columns={columns} rows={data?.options.data ?? []} rowKey={(r) => `${r.symbol}-${r.feature_ts}`} />
          )}
        </Card>
      )}
    </div>
  );
}
