import { useState, useMemo } from 'react';
import { SymbolPicker } from '../components/SymbolPicker';
import { api } from '../api/client';
import type { MarketSnapshot, OHLCVFeature } from '../api/types';
import { useApi } from '../hooks/useApi';
import { Card } from '../components/Card';
import { StatTile } from '../components/StatTile';
import { Table, type Column } from '../components/Table';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { FreshnessBadge } from '../components/FreshnessBadge';

const RANGE_OPTIONS = [
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: 'All', days: 0 },
] as const;

const ohlcvColumns: Column<OHLCVFeature>[] = [
  { key: 'ts', header: 'Date', render: (r) => r.event_date || '—' },
  { key: 'open', header: 'Open', render: (r) => (r.open ?? '—').toString() },
  { key: 'high', header: 'High', render: (r) => (r.high ?? '—').toString() },
  { key: 'low', header: 'Low', render: (r) => (r.low ?? '—').toString() },
  { key: 'close', header: 'Close', render: (r) => (r.close ?? '—').toString() },
  { key: 'volume', header: 'Volume', render: (r) => (r.volume ?? '—').toString() },
  { key: 'vwap', header: 'VWAP', render: (r) => (r.vwap ?? '—').toString() },
];

function formatDate(d: string): string {
  try {
    return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return d;
  }
}

function AdjCloseChart({ rows, symbol }: { rows: OHLCVFeature[]; symbol: string }) {
  const [range, setRange] = useState<(typeof RANGE_OPTIONS)[number]['label']>('All');

  const filtered = useMemo(() => {
    const sorted = [...rows].sort((a, b) => a.event_date.localeCompare(b.event_date));
    const opt = RANGE_OPTIONS.find((r) => r.label === range);
    if (!opt || opt.days === 0) return sorted;
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - opt.days);
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    return sorted.filter((r) => r.event_date >= cutoffStr);
  }, [rows, range]);

  if (filtered.length === 0) {
    return (
      <EmptyState
        title="No chart data"
        detail={`No OHLCV rows available for ${symbol} in the selected range.`}
      />
    );
  }

  const closes = filtered.map((r) => r.close ?? 0);
  const volumes = filtered.map((r) => r.volume ?? 0);
  const maxClose = Math.max(...closes);
  const minClose = Math.min(...closes);
  const closeRange = maxClose - minClose || 1;
  const maxVol = Math.max(...volumes) || 1;

  const width = 600;
  const height = 200;
  const padding = { top: 10, right: 50, bottom: 30, left: 10 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const xStep = filtered.length > 1 ? chartW / (filtered.length - 1) : chartW;
  const getX = (i: number) => padding.left + i * xStep;
  const getCloseY = (v: number) => padding.top + chartH - ((v - minClose) / closeRange) * chartH;
  const getVolY = (v: number) => padding.top + chartH - (v / maxVol) * chartH * 0.3;

  const linePath = filtered
    .map((r, i) => `${i === 0 ? 'M' : 'L'}${getX(i).toFixed(1)},${getCloseY(r.close ?? 0).toFixed(1)}`)
    .join(' ');

  const areaPath = `${linePath} L${getX(filtered.length - 1).toFixed(1)},${(padding.top + chartH).toFixed(1)} L${getX(0).toFixed(1)},${(padding.top + chartH).toFixed(1)} Z`;

  const tickIndices = filtered.length <= 6
    ? filtered.map((_, i) => i)
    : [0, Math.floor(filtered.length / 4), Math.floor(filtered.length / 2), Math.floor((3 * filtered.length) / 4), filtered.length - 1];

  return (
    <div>
      <div className="mb-2 flex items-center gap-1">
        {RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.label}
            type="button"
            onClick={() => setRange(opt.label)}
            className={`rounded-md px-2 py-0.5 text-xs font-medium transition-colors ${
              range === opt.label
                ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full"
          role="img"
          aria-label={`Adjusted close price chart for ${symbol}`}
          style={{ minWidth: 300, maxHeight: 220 }}
        >
          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
            const y = padding.top + chartH * (1 - frac);
            const val = minClose + closeRange * frac;
            return (
              <g key={frac}>
                <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="currentColor" strokeOpacity={0.08} />
                <text x={width - padding.right + 4} y={y + 3} className="text-[9px] fill-slate-400" style={{ fontSize: 9 }}>
                  {val.toFixed(1)}
                </text>
              </g>
            );
          })}

          {/* Volume bars */}
          {filtered.map((r, i) => {
            const x = getX(i) - xStep * 0.3;
            const barH = ((r.volume ?? 0) / maxVol) * chartH * 0.3;
            return (
              <rect
                key={`vol-${i}`}
                x={x}
                y={padding.top + chartH - barH}
                width={Math.max(xStep * 0.6, 1)}
                height={barH}
                fill="currentColor"
                opacity={0.12}
              />
            );
          })}

          {/* Area fill */}
          <path d={areaPath} fill="currentColor" opacity={0.06} />

          {/* Line */}
          <path d={linePath} fill="none" stroke="currentColor" strokeWidth={1.5} className="text-[var(--accent)]" />

          {/* X-axis labels */}
          {tickIndices.map((i) => (
            <text
              key={`tick-${i}`}
              x={getX(i)}
              y={height - 5}
              textAnchor="middle"
              className="text-[9px] fill-slate-400"
              style={{ fontSize: 9 }}
            >
              {formatDate(filtered[i].event_date)}
            </text>
          ))}
        </svg>
      </div>

      {/* Accessible fallback table (screen readers) */}
      <div className="overflow-x-auto">
      <table className="sr-only">
        <caption>Adjusted close and volume data for {symbol}</caption>
        <thead>
          <tr><th>Date</th><th>Close</th><th>Volume</th></tr>
        </thead>
        <tbody>
          {filtered.map((r) => (
            <tr key={r.event_date}>
              <td>{r.event_date}</td>
              <td>{r.close ?? '—'}</td>
              <td>{r.volume ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}

export function MarketDashboard() {
  const [symbol, setSymbol] = useState('NVDA');
  const { data, loading, error, reload } = useApi<MarketSnapshot>(
    () => api.market(symbol),
    [symbol],
  );

  const sortedOhlcv = useMemo(() => {
    if (!data) return [];
    return [...data.ohlcv.data].sort((a, b) => a.event_date.localeCompare(b.event_date));
  }, [data]);

  const latest = sortedOhlcv.length > 0 ? sortedOhlcv[sortedOhlcv.length - 1] : null;
  const hasCoverage = data ? !data.ohlcv.empty : undefined;

  return (
    <div data-tour="market-research" className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Market Dashboard</h1>
        <div className="flex items-center gap-2">
          {data && (
            <FreshnessBadge freshness={data.ohlcv.freshness} />
          )}
        </div>
      </div>

      <SymbolPicker value={symbol} onChange={setSymbol} list="market" hasCoverage={hasCoverage} />

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

          <Card
            title="Adjusted Close & Volume"
            subtitle={data?.ohlcv.source ?? 'silver_ohlcv_day_adjusted'}
            actions={
              <div className="flex items-center gap-2">
                {data && <FreshnessBadge freshness={data.ohlcv.freshness} />}
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {sortedOhlcv.length} rows
                </span>
              </div>
            }
          >
            {data && data.ohlcv.empty ? (
              <EmptyState
                title="No market features yet"
                detail={`silver_ohlcv_day_adjusted is empty for ${symbol} — features appear once the silver→gold pipeline has run.`}
              />
            ) : (
              <AdjCloseChart rows={sortedOhlcv} symbol={symbol} />
            )}
          </Card>

          <Card title="OHLCV Features" subtitle="silver_ohlcv_day_adjusted" actions={<FreshnessBadge freshness={data ? data.ohlcv.freshness : { state: 'empty', table: '', detail: '' }} />}>
            {data && data.ohlcv.empty ? (
              <EmptyState
                title="No market features yet"
                detail={`silver_ohlcv_day_adjusted is empty for ${symbol} — features appear once the silver→gold pipeline has run.`}
              />
            ) : (
              <Table columns={ohlcvColumns} rows={sortedOhlcv} rowKey={(r) => r.event_date || r.symbol} />
            )}
          </Card>
        </>
      )}
    </div>
  );
}