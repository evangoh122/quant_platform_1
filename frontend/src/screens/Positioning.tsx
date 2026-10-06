import { useState, useMemo } from 'react';
import { SymbolPicker } from '../components/SymbolPicker';
import { api } from '../api/client';
import type {
  PositioningResponse,
  CotWeeklyRow,
  CotContractRow,
  MarketSnapshot,
  OptionsFeature,
} from '../api/types';
import { useApi } from '../hooks/useApi';
import { Card } from '../components/Card';
import { StatTile } from '../components/StatTile';
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
} from '../components/charts';

const ASSET_CLASSES = [
  'equity_index',
  'rate',
  'fx',
  'other',
  'crypto',
  'commodity',
] as const;

type AssetClass = (typeof ASSET_CLASSES)[number];

function formatDate(d: string): string {
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
  } catch {
    return d;
  }
}

function formatNum(v: number | null | undefined): string {
  if (v == null) return '—';
  return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatPct(v: number | null | undefined): string {
  if (v == null) return '—';
  return v.toFixed(1) + '%';
}

/* ── Net Positions Line Chart ──────────────────────────────────────────────── */

interface NetPositionsChartProps {
  rows: CotWeeklyRow[];
}

function NetPositionsChart({ rows }: NetPositionsChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const sorted = useMemo(
    () => [...rows].sort((a, b) => a.information_available_ts.localeCompare(b.information_available_ts)),
    [rows],
  );

  if (sorted.length === 0) {
    return <EmptyState title="No chart data" detail="No COT weekly rows available." />;
  }

  const lmVals = sorted.map((r) => r.lev_money_net).filter((v): v is number => v != null);
  const amVals = sorted.map((r) => r.asset_mgr_net).filter((v): v is number => v != null);
  const allVals = [...lmVals, ...amVals];
  const [yMin, yMax] = allVals.length > 0
    ? niceExtent(Math.min(...allVals), Math.max(...allVals))
    : [-100000, 100000];

  const width = 600;
  const height = 220;
  const padding = { top: 10, right: 14, bottom: 30, left: 50 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const n = sorted.length;
  const xStep = n > 1 ? chartW / (n - 1) : chartW;
  const getX = (i: number) => padding.left + i * xStep;
  const yScale = linearScale({ min: yMin, max: yMax }, { start: padding.top + chartH, end: padding.top });

  const lmData = sorted.map((r, i) => ({ x: getX(i), y: r.lev_money_net }));
  const amData = sorted.map((r, i) => ({ x: getX(i), y: r.asset_mgr_net }));

  const tickIdxs =
    n <= 6
      ? sorted.map((_, i) => i)
      : [0, Math.floor(n / 4), Math.floor(n / 2), Math.floor((3 * n) / 4), n - 1];

  const tableData = {
    headers: ['Date (release)', 'Report Date', 'Lev Money Net', 'Asset Mgr Net', 'Crowding', 'Regime'],
    rows: sorted.map((r) => [
      formatDate(r.information_available_ts),
      formatDate(r.report_date),
      formatNum(r.lev_money_net),
      formatNum(r.asset_mgr_net),
      r.crowding_score?.toFixed(2) ?? '—',
      r.regime_label ?? '—',
    ]),
  };

  return (
    <ChartFrame
      title="Leveraged Money vs Asset Manager Net Positions"
      caption="CFTC COT weekly · futures positioning by trader category"
      legend={[
        { label: 'Leveraged Money', color: '#3b82f6' },
        { label: 'Asset Manager', color: '#10b981' },
      ]}
      tableData={tableData}
      width={width}
      height={height}
      ariaLabel="Net positions line chart"
    >
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

      <LineSeries
        data={lmData}
        getX={(i) => lmData[i].x}
        getY={(v) => yScale(v)}
        stroke="#3b82f6"
        strokeWidth={1.5}
        ariaLabel="Leveraged money net line"
      />
      <LineSeries
        data={amData}
        getX={(i) => amData[i].x}
        getY={(v) => yScale(v)}
        stroke="#10b981"
        strokeWidth={1.5}
        ariaLabel="Asset manager net line"
      />

      {sorted.map((r, i) => (
        <Tooltip
          key={i}
          content={`${formatDate(r.information_available_ts)} · LM ${formatNum(r.lev_money_net)} · AM ${formatNum(r.asset_mgr_net)}`}
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

      <XAxis
        domain={{ min: 0, max: n - 1 }}
        range={{ start: padding.left, end: width - padding.right }}
        y={padding.top + chartH}
        labels={tickIdxs.map((i) => formatDate(sorted[i].information_available_ts))}
      />
      <YAxis
        domain={{ min: yMin, max: yMax }}
        range={{ start: padding.top, end: padding.top + chartH }}
        x={padding.left}
        tickCount={4}
        format={(v) => (v / 1000).toFixed(0) + 'k'}
      />

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

/* ── Percentile Band Chart ─────────────────────────────────────────────────── */

interface PercentileChartProps {
  rows: CotWeeklyRow[];
}

function PercentileChart({ rows }: PercentileChartProps) {
  const sorted = useMemo(
    () => [...rows].sort((a, b) => a.information_available_ts.localeCompare(b.information_available_ts)),
    [rows],
  );

  const pctileVals = sorted
    .map((r) => r.lev_money_pctile_52w)
    .filter((v): v is number => v != null);

  if (pctileVals.length === 0) {
    return <EmptyState title="No percentile data" detail="lev_money_pctile_52w is all null." />;
  }

  const width = 600;
  const height = 140;
  const padding = { top: 10, right: 14, bottom: 24, left: 50 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const n = sorted.length;
  const xStep = n > 1 ? chartW / (n - 1) : chartW;
  const getX = (i: number) => padding.left + i * xStep;
  const yScale = linearScale({ min: 0, max: 100 }, { start: padding.top + chartH, end: padding.top });

  const pctData = sorted.map((r, i) => ({ x: getX(i), y: r.lev_money_pctile_52w }));

  const tickIdxs =
    n <= 6
      ? sorted.map((_, i) => i)
      : [0, Math.floor(n / 4), Math.floor(n / 2), Math.floor((3 * n) / 4), n - 1];

  return (
    <ChartFrame
      title="52-Week Percentile (Leveraged Money Net)"
      caption="Percentile rank within trailing 52 weeks"
      width={width}
      height={height}
      ariaLabel="52-week percentile chart"
    >
      {/* Band: 25-75 percentile zone */}
      <rect
        x={padding.left}
        y={yScale(75)}
        width={chartW}
        height={yScale(25) - yScale(75)}
        fill="currentColor"
        opacity={0.05}
      />

      <LineSeries
        data={pctData}
        getX={(i) => pctData[i].x}
        getY={(v) => yScale(v)}
        stroke="#f59e0b"
        strokeWidth={1.5}
        ariaLabel="Percentile line"
      />

      <XAxis
        domain={{ min: 0, max: n - 1 }}
        range={{ start: padding.left, end: width - padding.right }}
        y={padding.top + chartH}
        labels={tickIdxs.map((i) => formatDate(sorted[i].information_available_ts))}
      />
      <YAxis
        domain={{ min: 0, max: 100 }}
        range={{ start: padding.top, end: padding.top + chartH }}
        x={padding.left}
        tickCount={3}
        format={(v) => v.toFixed(0) + '%'}
      />
    </ChartFrame>
  );
}

/* ── Contract Diverging Bar Chart ──────────────────────────────────────────── */

interface ContractBarChartProps {
  rows: CotContractRow[];
}

function ContractBarChart({ rows }: ContractBarChartProps) {
  const sorted = useMemo(
    () => [...rows].sort((a, b) => Math.abs(b.lev_money_pct_oi ?? 0) - Math.abs(a.lev_money_pct_oi ?? 0)),
    [rows],
  );

  if (sorted.length === 0) {
    return <EmptyState title="No contract data" detail="No silver_cot_positions rows." />;
  }

  const display = sorted.slice(0, 15);
  const maxAbs = Math.max(...display.map((r) => Math.abs(r.lev_money_pct_oi ?? 0)), 5);

  const width = 600;
  const barH = 22;
  const gap = 4;
  const padding = { top: 10, right: 60, bottom: 10, left: 140 };
  const height = padding.top + padding.bottom + display.length * (barH + gap);
  const chartW = width - padding.left - padding.right;
  const midX = padding.left + chartW / 2;
  const xScale = linearScale({ min: -maxAbs, max: maxAbs }, { start: padding.left, end: width - padding.right });

  return (
    <ChartFrame
      title="Net % of OI by Participant (Latest Week)"
      caption="Sorted by |leveraged money % OI| · diverging bars"
      width={width}
      height={height}
      ariaLabel="Contract diverging bar chart"
    >
      {/* Center line */}
      <line
        x1={midX}
        y1={padding.top}
        x2={midX}
        y2={height - padding.bottom}
        stroke="currentColor"
        strokeOpacity={0.15}
      />

      {display.map((r, i) => {
        const y = padding.top + i * (barH + gap);
        const lmPct = r.lev_money_pct_oi ?? 0;
        const amPct = r.asset_mgr_pct_oi ?? 0;
        const dlPct = r.dealer_pct_oi ?? 0;
        const lmW = Math.abs(lmPct) / maxAbs * (chartW / 2);
        const amW = Math.abs(amPct) / maxAbs * (chartW / 2);
        const dlW = Math.abs(dlPct) / maxAbs * (chartW / 2);

        return (
          <g key={r.contract_name}>
            <text
              x={padding.left - 4}
              y={y + barH / 2 + 3}
              textAnchor="end"
              className="fill-slate-500 dark:fill-slate-400"
              style={{ fontSize: 10 }}
            >
              {r.contract_name.length > 18 ? r.contract_name.slice(0, 18) + '…' : r.contract_name}
            </text>

            {/* Leveraged money bar */}
            <rect
              x={lmPct >= 0 ? midX : midX - lmW}
              y={y}
              width={Math.max(lmW, 1)}
              height={barH * 0.3}
              fill="#3b82f6"
              opacity={0.7}
            >
              <title>{`LM: ${formatPct(lmPct)}`}</title>
            </rect>

            {/* Asset manager bar */}
            <rect
              x={amPct >= 0 ? midX : midX - amW}
              y={y + barH * 0.35}
              width={Math.max(amW, 1)}
              height={barH * 0.3}
              fill="#10b981"
              opacity={0.7}
            >
              <title>{`AM: ${formatPct(amPct)}`}</title>
            </rect>

            {/* Dealer bar */}
            <rect
              x={dlPct >= 0 ? midX : midX - dlW}
              y={y + barH * 0.7}
              width={Math.max(dlW, 1)}
              height={barH * 0.3}
              fill="#ef4444"
              opacity={0.7}
            >
              <title>{`Dealer: ${formatPct(dlPct)}`}</title>
            </rect>

            {/* Right labels */}
            <text
              x={width - padding.right + 4}
              y={y + barH / 2 + 3}
              className="fill-slate-400"
              style={{ fontSize: 9 }}
            >
              {formatPct(lmPct)}
            </text>
          </g>
        );
      })}

      {/* Zero label */}
      <text
        x={midX}
        y={height - 2}
        textAnchor="middle"
        className="fill-slate-400"
        style={{ fontSize: 8 }}
      >
        0%
      </text>
    </ChartFrame>
  );
}

/* ── Options Positioning Card ──────────────────────────────────────────────── */

interface OptionsPositioningCardProps {
  symbol: string;
}

function OptionsPositioningCard({ symbol }: OptionsPositioningCardProps) {
  const { data, loading, error, reload } = useApi<MarketSnapshot>(
    () => api.market(symbol),
    [symbol],
  );

  const sortedOptions = useMemo(() => {
    if (!data) return [];
    return [...data.options.data].sort((a, b) => a.feature_ts.localeCompare(b.feature_ts));
  }, [data]);

  const densePcr = useMemo(
    () => sortedOptions.filter((r) => r.put_call_ratio != null),
    [sortedOptions],
  );

  const oiSnapshot = useMemo(() => {
    for (let i = sortedOptions.length - 1; i >= 0; i--) {
      if (sortedOptions[i].oi_concentration != null) return sortedOptions[i];
    }
    return null;
  }, [sortedOptions]);

  const ndeSnapshot = useMemo(() => {
    for (let i = sortedOptions.length - 1; i >= 0; i--) {
      if (sortedOptions[i].net_delta_exposure != null) return sortedOptions[i];
    }
    return null;
  }, [sortedOptions]);

  if (loading) return <LoadingState label="Loading options…" />;
  if (error) return <ErrorState message={error} onRetry={reload} />;

  return (
    <Card
      title="Options Positioning"
      subtitle={`${symbol} · gold_options_features`}
    >
      {sortedOptions.length === 0 ? (
        <EmptyState title="No options data" detail={`No options features for ${symbol}.`} />
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <StatTile
              label="Put/Call Ratio (latest)"
              value={sortedOptions[sortedOptions.length - 1].put_call_ratio?.toFixed(4) ?? '—'}
              hint={formatDate(sortedOptions[sortedOptions.length - 1].feature_ts)}
            />
            <StatTile
              label="OI Concentration"
              value={oiSnapshot?.oi_concentration?.toFixed(4) ?? '—'}
              hint={oiSnapshot ? `snapshot ${formatDate(oiSnapshot.feature_ts)}` : undefined}
            />
            <StatTile
              label="Net Delta Exposure"
              value={ndeSnapshot?.net_delta_exposure?.toFixed(4) ?? '—'}
              hint={ndeSnapshot ? `snapshot ${formatDate(ndeSnapshot.feature_ts)}` : undefined}
            />
          </div>

          {(oiSnapshot != null || ndeSnapshot != null) && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              OI concentration and net delta exposure are snapshot only — no history available.
            </p>
          )}

          {densePcr.length > 1 && <PutCallRatioChart rows={densePcr} symbol={symbol} />}
        </div>
      )}
    </Card>
  );
}

/* ── Put/Call Ratio Trend Chart ────────────────────────────────────────────── */

interface PutCallRatioChartProps {
  rows: OptionsFeature[];
  symbol: string;
}

function PutCallRatioChart({ rows, symbol }: PutCallRatioChartProps) {
  const sorted = useMemo(
    () => [...rows].sort((a, b) => a.feature_ts.localeCompare(b.feature_ts)),
    [rows],
  );

  const pcrVals = sorted.map((r) => r.put_call_ratio).filter((v): v is number => v != null);
  const [pcrMin, pcrMax] = pcrVals.length > 0
    ? niceExtent(Math.min(...pcrVals), Math.max(...pcrVals))
    : [0, 1];

  const width = 500;
  const height = 160;
  const padding = { top: 10, right: 14, bottom: 24, left: 50 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const n = sorted.length;
  const xStep = n > 1 ? chartW / (n - 1) : chartW;
  const getX = (i: number) => padding.left + i * xStep;
  const yScale = linearScale({ min: pcrMin, max: pcrMax }, { start: padding.top + chartH, end: padding.top });

  const pcrData = sorted.map((r, i) => ({ x: getX(i), y: r.put_call_ratio }));

  const tickIdxs =
    n <= 6
      ? sorted.map((_, i) => i)
      : [0, Math.floor(n / 4), Math.floor(n / 2), Math.floor((3 * n) / 4), n - 1];

  return (
    <ChartFrame
      title="Put/Call Ratio Trend"
      caption={`gold_options_features · ${symbol} · dense P/C data`}
      width={width}
      height={height}
      ariaLabel="Put/call ratio trend chart"
    >
      <LineSeries
        data={pcrData}
        getX={(i) => pcrData[i].x}
        getY={(v) => yScale(v)}
        stroke="#8b5cf6"
        strokeWidth={1.5}
        ariaLabel="Put/call ratio line"
      />

      <XAxis
        domain={{ min: 0, max: n - 1 }}
        range={{ start: padding.left, end: width - padding.right }}
        y={padding.top + chartH}
        labels={tickIdxs.map((i) => formatDate(sorted[i].feature_ts))}
      />
      <YAxis
        domain={{ min: pcrMin, max: pcrMax }}
        range={{ start: padding.top, end: padding.top + chartH }}
        x={padding.left}
        tickCount={3}
        format={(v) => v.toFixed(2)}
      />
    </ChartFrame>
  );
}

/* ── Main Screen ───────────────────────────────────────────────────────────── */

export function Positioning() {
  const [assetClass, setAssetClass] = useState<AssetClass>('equity_index');
  const [optionsSymbol, setOptionsSymbol] = useState('SPY');

  const { data, loading, error, reload } = useApi<PositioningResponse>(
    () => api.positioning(assetClass, 156),
    [assetClass],
  );

  const latestWeek = useMemo(() => {
    if (!data || data.weekly.data.length === 0) return null;
    const sorted = [...data.weekly.data].sort(
      (a, b) => a.information_available_ts.localeCompare(b.information_available_ts),
    );
    return sorted[sorted.length - 1];
  }, [data]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Positioning</h1>
        {data && <FreshnessBadge freshness={data.weekly.freshness} />}
      </div>

      {/* Asset class selector */}
      <div className="flex flex-wrap gap-2">
        {ASSET_CLASSES.map((ac) => (
          <button
            key={ac}
            type="button"
            onClick={() => setAssetClass(ac)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              ac === assetClass
                ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
            }`}
          >
            {ac.replace('_', ' ')}
          </button>
        ))}
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && data && (
        <>
          {/* Stat tiles */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatTile
              label="Crowding Score"
              value={latestWeek?.crowding_score?.toFixed(2) ?? '—'}
              hint={latestWeek ? `report ${formatDate(latestWeek.report_date)}` : undefined}
            />
            <StatTile
              label="Regime"
              value={latestWeek?.regime_label ?? '—'}
              hint={latestWeek ? `released ${formatDate(latestWeek.information_available_ts)}` : undefined}
            />
            <StatTile
              label="Lev Money Net"
              value={formatNum(latestWeek?.lev_money_net)}
              hint={latestWeek?.lev_money_zscore_52w != null ? `z ${latestWeek.lev_money_zscore_52w.toFixed(2)}` : undefined}
            />
            <StatTile
              label="Asset Mgr Net"
              value={formatNum(latestWeek?.asset_mgr_net)}
              hint={latestWeek?.asset_mgr_pctile_52w != null ? `pctile ${latestWeek.asset_mgr_pctile_52w.toFixed(0)}%` : undefined}
            />
          </div>

          {/* Net positions chart */}
          <Card
            title="Net Positions Over Time"
            subtitle="gold_cot_features · leveraged money vs asset manager"
            actions={data && <FreshnessBadge freshness={data.weekly.freshness} />}
          >
            {data.weekly.empty ? (
              <EmptyState
                title="No COT data"
                detail={`gold_cot_features has no rows for ${assetClass}.`}
              />
            ) : (
              <NetPositionsChart rows={data.weekly.data} />
            )}
          </Card>

          {/* Percentile chart */}
          {!data.weekly.empty && (
            <Card title="52-Week Percentile Band">
              <PercentileChart rows={data.weekly.data} />
            </Card>
          )}

          {/* Contract diverging bar chart */}
          <Card
            title="Contract-Level Breakdown"
            subtitle="silver_cot_positions · net % of OI by participant"
            actions={data && <FreshnessBadge freshness={data.contracts.freshness} />}
          >
            {data.contracts.empty ? (
              <EmptyState
                title="No contract data"
                detail={`silver_cot_positions has no rows for ${assetClass}.`}
              />
            ) : (
              <ContractBarChart rows={data.contracts.data} />
            )}
          </Card>

          {/* Options positioning card */}
          <OptionsPositioningCard symbol={optionsSymbol} />

          {/* Symbol picker for options */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 dark:text-slate-400">Options symbol:</span>
            <SymbolPicker
              value={optionsSymbol}
              onChange={setOptionsSymbol}
              list="options"
              label=""
            />
          </div>

          {/* Caption */}
          <p className="text-xs text-slate-400 dark:text-slate-500">
            CFTC data are weekly, released Fridays for the prior Tuesday; futures positioning by trader category, not single-stock holdings.
          </p>
        </>
      )}
    </div>
  );
}