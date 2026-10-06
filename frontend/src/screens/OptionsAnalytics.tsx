import { useState, useMemo } from 'react';
import { SymbolPicker } from '../components/SymbolPicker';
import { api } from '../api/client';
import type { MarketSnapshot, OptionsFeature } from '../api/types';
import { useApi } from '../hooks/useApi';
import { Card } from '../components/Card';
import { StatTile } from '../components/StatTile';
import { Table, type Column } from '../components/Table';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { FreshnessBadge } from '../components/FreshnessBadge';
import {
  ChartFrame,
  LineSeries,
  BarSeries,
  XAxis,
  YAxis,
  Tooltip,
  linearScale,
  niceExtent,
  tickValues,
} from '../components/charts';

function formatDate(d: string): string {
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return d;
  }
}

const tableColumns: Column<OptionsFeature>[] = [
  { key: 'ts', header: 'Date', render: (r) => formatDate(r.feature_ts) },
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
];

interface OptionsChartProps {
  rows: OptionsFeature[];
  symbol: string;
}

function OptionsTimelineChart({ rows, symbol }: OptionsChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const sorted = useMemo(
    () => [...rows].sort((a, b) => a.feature_ts.localeCompare(b.feature_ts)),
    [rows],
  );

  if (sorted.length === 0) {
    return <EmptyState title="No chart data" detail={`No options rows available for ${symbol}.`} />;
  }

  const putVols = sorted.map((r) => r.put_volume ?? 0);
  const callVols = sorted.map((r) => r.call_volume ?? 0);
  const ratios = sorted.map((r) => r.put_call_ratio);
  const zscores = sorted.map((r) => r.volume_anomaly_zscore);

  const maxVol = Math.max(...putVols, ...callVols, 1);
  const ratioVals = ratios.filter((v): v is number => v != null);
  const zscoreVals = zscores.filter((v): v is number => v != null);
  const [ratioMin, ratioMax] = ratioVals.length > 0
    ? niceExtent(Math.min(...ratioVals), Math.max(...ratioVals))
    : [0, 1];
  const [zMin, zMax] = zscoreVals.length > 0
    ? niceExtent(Math.min(...zscoreVals), Math.max(...zscoreVals))
    : [-3, 3];

  const width = 600;
  const height = 260;
  const padding = { top: 10, right: 50, bottom: 30, left: 10 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const n = sorted.length;
  const xStep = n > 1 ? chartW / (n - 1) : chartW;
  const getX = (i: number) => padding.left + i * xStep;

  const volScale = linearScale({ min: 0, max: maxVol }, { start: padding.top + chartH, end: padding.top });
  const ratioScale = linearScale(
    { min: ratioMin, max: ratioMax },
    { start: padding.top + chartH, end: padding.top },
  );
  const zScale = linearScale(
    { min: zMin, max: zMax },
    { start: padding.top + chartH, end: padding.top },
  );

  const barW = Math.max(xStep * 0.5, 2);
  const barX = (i: number) => getX(i) - barW / 2;
  const bottom = padding.top + chartH;

  const putBars = sorted.map((r, i) => {
    if (r.put_volume == null) return null;
    return {
      x: barX(i),
      y: volScale(r.put_volume),
      width: barW,
      height: bottom - volScale(r.put_volume),
      fill: '#ef4444',
      label: `Put: ${r.put_volume.toLocaleString()}`,
    };
  });

  const callBars = sorted.map((r, i) => {
    if (r.call_volume == null) return null;
    const putVol = r.put_volume ?? 0;
    return {
      x: barX(i),
      y: volScale(putVol + r.call_volume),
      width: barW,
      height: volScale(putVol) - volScale(putVol + r.call_volume),
      fill: '#22c55e',
      label: `Call: ${r.call_volume.toLocaleString()}`,
    };
  });

  const ratioData = sorted.map((r, i) => ({ x: getX(i), y: r.put_call_ratio }));
  const zscoreData = sorted.map((r, i) => ({ x: getX(i), y: r.volume_anomaly_zscore }));

  const tickIdxs =
    n <= 6
      ? sorted.map((_, i) => i)
      : [0, Math.floor(n / 4), Math.floor(n / 2), Math.floor((3 * n) / 4), n - 1];

  const tableData = {
    headers: ['Date', 'Put Vol', 'Call Vol', 'P/C Ratio', 'Vol Anomaly Z'],
    rows: sorted.map((r) => [
      r.feature_ts,
      r.put_volume ?? '—',
      r.call_volume ?? '—',
      r.put_call_ratio?.toFixed(4) ?? '—',
      r.volume_anomaly_zscore?.toFixed(2) ?? '—',
    ]),
  };

  return (
    <ChartFrame
      title="Put/Call Timeline"
      caption={`gold_options_features · ${symbol}`}
      legend={[
        { label: 'Put Volume', color: '#ef4444' },
        { label: 'Call Volume', color: '#22c55e' },
        { label: 'P/C Ratio', color: '#8b5cf6' },
        { label: 'Vol Anomaly Z', color: '#f59e0b', dashed: true },
      ]}
      tableData={tableData}
      width={width}
      height={height}
      ariaLabel={`Options put/call timeline chart for ${symbol}`}
    >
      {/* Grid lines */}
      {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
        const y = padding.top + chartH * (1 - frac);
        return (
          <line
            key={frac}
            x1={padding.left}
            y1={y}
            x2={width - padding.right}
            y2={y}
            stroke="currentColor"
            strokeOpacity={0.08}
          />
        );
      })}

      {/* Stacked volume bars */}
      <BarSeries bars={putBars.filter((b): b is NonNullable<typeof b> => b != null)} ariaLabel="Put volume bars" />
      <BarSeries bars={callBars.filter((b): b is NonNullable<typeof b> => b != null)} ariaLabel="Call volume bars" />

      {/* Ratio line */}
      <LineSeries
        data={ratioData}
        getX={(i) => ratioData[i].x}
        getY={(v) => ratioScale(v)}
        stroke="#8b5cf6"
        strokeWidth={1.5}
        ariaLabel="Put/call ratio line"
      />

      {/* Volume anomaly z-score line */}
      <LineSeries
        data={zscoreData}
        getX={(i) => zscoreData[i].x}
        getY={(v) => zScale(v)}
        stroke="#f59e0b"
        strokeWidth={1.5}
        ariaLabel="Volume anomaly z-score line"
      />

      {/* Hover targets */}
      {sorted.map((r, i) => (
        <Tooltip
          key={i}
          content={`${formatDate(r.feature_ts)} · P/C ${r.put_call_ratio?.toFixed(3) ?? '—'}`}
          x={getX(i)}
          y={padding.top + chartH / 2}
          chartWidth={width}
          chartHeight={height}
        >
          <rect
            x={getX(i) - xStep / 2}
            y={padding.top}
            width={xStep}
            height={chartH}
            fill="transparent"
            onMouseEnter={() => setHoverIdx(i)}
            onMouseLeave={() => setHoverIdx(null)}
          />
        </Tooltip>
      ))}

      {/* X-axis */}
      <XAxis
        domain={{ min: 0, max: n - 1 }}
        range={{ start: padding.left, end: width - padding.right }}
        y={padding.top + chartH}
        labels={tickIdxs.map((i) => formatDate(sorted[i].feature_ts))}
      />

      {/* Right axis labels for ratio */}
      {tickValues(ratioMin, ratioMax, 3).map((v, i) => {
        const y = ratioScale(v);
        return (
          <text
            key={`ratio-${i}`}
            x={width - padding.right + 4}
            y={y + 3}
            className="fill-purple-400"
            style={{ fontSize: 8 }}
          >
            {v.toFixed(2)}
          </text>
        );
      })}

      {/* Hover indicator */}
      {hoverIdx !== null && (
        <line
          x1={getX(hoverIdx)}
          y1={padding.top}
          x2={getX(hoverIdx)}
          y2={padding.top + chartH}
          stroke="currentColor"
          strokeOpacity={0.15}
          strokeDasharray="2,2"
        />
      )}
    </ChartFrame>
  );
}

export function OptionsAnalytics() {
  const [symbol, setSymbol] = useState('NVDA');
  const { data, loading, error, reload } = useApi<MarketSnapshot>(
    () => api.market(symbol),
    [symbol],
  );

  const hasCoverage = data ? !data.options.empty : undefined;

  const sortedOptions = useMemo(() => {
    if (!data) return [];
    return [...data.options.data].sort((a, b) => a.feature_ts.localeCompare(b.feature_ts));
  }, [data]);

  const latestIvRow = useMemo(() => {
    if (sortedOptions.length === 0) return null;
    for (let i = sortedOptions.length - 1; i >= 0; i--) {
      if (sortedOptions[i].iv_atm != null) return sortedOptions[i];
    }
    return null;
  }, [sortedOptions]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Options Analytics</h1>
        {data && <FreshnessBadge freshness={data.options.freshness} />}
      </div>

      <SymbolPicker value={symbol} onChange={setSymbol} list="options" hasCoverage={hasCoverage} />

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatTile
              label="ATM IV"
              value={latestIvRow?.iv_atm?.toFixed(4) ?? '—'}
              hint={latestIvRow ? formatDate(latestIvRow.feature_ts) : undefined}
            />
            <StatTile
              label="IV Skew"
              value={latestIvRow?.iv_skew?.toFixed(4) ?? '—'}
            />
            <StatTile
              label="Put/Call Ratio"
              value={sortedOptions.length > 0 ? (sortedOptions[sortedOptions.length - 1].put_call_ratio?.toFixed(4) ?? '—') : '—'}
            />
            <StatTile
              label="Vol Anomaly Z"
              value={sortedOptions.length > 0 ? (sortedOptions[sortedOptions.length - 1].volume_anomaly_zscore?.toFixed(2) ?? '—') : '—'}
            />
          </div>

          <Card
            title="Put/Call Timeline"
            subtitle="gold_options_features · stacked volume + ratio + anomaly"
            actions={
              <div className="flex items-center gap-2">
                {data && <FreshnessBadge freshness={data.options.freshness} />}
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {sortedOptions.length} rows
                </span>
              </div>
            }
          >
            {data && data.options.empty ? (
              <EmptyState
                title="No options features yet"
                detail={`gold_options_features is empty for ${symbol} — IV, skew and volume anomalies appear after the options gold transform runs.`}
              />
            ) : (
              <OptionsTimelineChart rows={sortedOptions} symbol={symbol} />
            )}
          </Card>

          <Card
            title="Options Chain Metrics"
            subtitle="gold_options_features · IV / skew / unusual volume"
          >
            {data && data.options.empty ? (
              <EmptyState
                title="No options features yet"
                detail={`gold_options_features is empty for ${symbol} — IV, skew and volume anomalies appear after the options gold transform runs.`}
              />
            ) : (
              <Table columns={tableColumns} rows={sortedOptions} rowKey={(r) => `${r.symbol}-${r.feature_ts}`} />
            )}
          </Card>
        </>
      )}
    </div>
  );
}