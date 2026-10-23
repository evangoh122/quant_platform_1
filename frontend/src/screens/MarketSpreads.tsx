import { useState } from 'react';
import { api } from '../api/client';
import type { MarketSpreadsResponse, SpreadChart } from '../api/types';
import { useApi } from '../hooks/useApi';
import { Card } from '../components/Card';
import { StatTile } from '../components/StatTile';
import { FreshnessBadge } from '../components/FreshnessBadge';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { Eyebrow } from '../components/Eyebrow';
import { LineChart, type LineChartSeries } from '../components/LineChart';

// The requested window is TRADING days (weekday approximation), not calendar
// days: 21 / 63 / 126 approximate one / three / six months of trading.
const RANGE_OPTIONS = [
  { label: '1M', days: 21 },
  { label: '3M', days: 63 },
  { label: '6M', days: 126 },
  { label: 'All', days: 1000 },
] as const;

const SERIES_TOKENS = ['--accent', '--neutral'];

function fmt(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return value.toFixed(digits);
}

function fmtPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function toLines(chart: SpreadChart): LineChartSeries[] {
  return chart.series.map((series, index) => ({
    key: series.key,
    label: series.label,
    points: series.points,
    colorVar: SERIES_TOKENS[index % SERIES_TOKENS.length],
    dashed: index > 0,
  }));
}

/** Tile value plus the API's own unit (`pp` for a yield spread). */
function fmtTile(value: number | null | undefined, unit: string | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return unit ? `${fmt(value)} ${unit}` : fmt(value);
}

/** Screen-reader summary: latest value(s), window change and as-of date. */
function chartSummary(chart: SpreadChart): string {
  if (chart.empty) {
    return `${chart.title}: no data in the selected window.`;
  }
  if (chart.kind === 'yield') {
    const ten = chart.series[0]?.latest_value;
    const two = chart.series[1]?.latest_value;
    return (
      `${chart.title}: 10Y ${fmt(ten)}%, 2Y ${fmt(two)}%, ` +
      `10s2s ${fmtTile(chart.tile?.value, chart.tile?.unit)} as of ${chart.as_of ?? '—'}.`
    );
  }
  const series = chart.series[0];
  if (chart.kind === 'price') {
    return (
      `${chart.title}: latest ${fmt(series?.latest_value)} ${chart.unit} as of ` +
      `${chart.as_of ?? '—'}, window change ${fmtPct(series?.window_pct_change)}.`
    );
  }
  return (
    `${chart.title}: index ${fmt(series?.latest_value)} ` +
    `(100 = first common date ${chart.first_common_date ?? '—'}) as of ` +
    `${chart.as_of ?? '—'}, window change ${fmtPct(series?.window_pct_change)}.`
  );
}

function emptyDetail(chart: SpreadChart): string {
  if (chart.freshness.state === 'unavailable') {
    return `${chart.source} is unavailable. Nothing is shown rather than a zero.`;
  }
  if (chart.first_common_date) {
    return (
      `Fewer than two usable points in this window. First common date: ` +
      `${chart.first_common_date}.`
    );
  }
  return 'No usable values in this window.';
}

function SpreadChartCard({ chart }: { chart: SpreadChart }) {
  return (
    <Card
      title={chart.title}
      subtitle={chart.subtitle}
      actions={<FreshnessBadge freshness={chart.freshness} />}
    >
      {chart.empty ? (
        <EmptyState title="No data for this window" detail={emptyDetail(chart)} />
      ) : (
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px]">
          <LineChart
            series={toLines(chart)}
            ariaLabel={`${chart.title} chart`}
            summary={chartSummary(chart)}
            unit={chart.unit}
            formatter={(value) => fmt(value)}
          />
          {chart.tile && (
            <div className="space-y-2">
              <StatTile
                label={chart.tile.label}
                value={fmtTile(chart.tile.value, chart.tile.unit)}
                hint={chart.tile.as_of ? `as of ${chart.tile.as_of}` : undefined}
              />
            </div>
          )}
        </div>
      )}

      {chart.dropped_dates > 0 && (
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          {chart.dropped_dates} date{chart.dropped_dates === 1 ? '' : 's'} missing in one leg —
          dropped, not forward-filled.
        </p>
      )}
      {chart.caption && (
        <p className="mt-2 text-xs text-[var(--text-secondary)]">{chart.caption}</p>
      )}
    </Card>
  );
}

export function MarketSpreads() {
  const [range, setRange] = useState<(typeof RANGE_OPTIONS)[number]['label']>('All');
  const days = RANGE_OPTIONS.find((option) => option.label === range)?.days ?? 1000;
  const { data, loading, error, reload } = useApi<MarketSpreadsResponse>(
    () => api.spreads(days),
    [days],
  );

  // A payload without `charts` (an older or degraded API shape) must degrade to
  // the empty state: reading `data.charts.map` on it threw a TypeError into the
  // app shell, which has no error boundary. The futures gap card is static
  // content about a named gap, so it stays visible either way.
  const charts = data?.charts ?? [];

  return (
    <div className="space-y-4">
      <div className="min-w-0">
        <Eyebrow>relative value, not a signal</Eyebrow>
        <h1 className="mt-1.5 text-xl font-semibold tracking-tight">Cross-asset spreads</h1>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-[var(--text-muted)]">
          Window: last {days} trading days (weekday approximation — exchange holidays are not
          excluded).{data ? ` ${data.window_start} to ${data.window_end}.` : ''}
        </p>
        <div className="flex items-center gap-1" role="group" aria-label="Chart window">
          {RANGE_OPTIONS.map((option) => (
            <button
              key={option.label}
              type="button"
              aria-pressed={range === option.label}
              onClick={() => setRange(option.label)}
              className={`rounded-md px-2 py-0.5 text-xs font-medium transition-colors ${
                range === option.label
                  ? 'bg-[var(--accent)] text-[var(--accent-ink)]'
                  : 'bg-[var(--surface-raised)] text-[var(--text-secondary)] hover:bg-[var(--border-subtle)]'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {loading && <LoadingState label="Loading spreads…" />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && charts.length === 0 && (
        <EmptyState title="No spreads data" detail="The API returned no charts." />
      )}
      {!loading &&
        !error &&
        charts.map((chart) => <SpreadChartCard key={chart.chart_id} chart={chart} />)}
      {!loading && !error && (
        <Card title="CLZ26.NYM vs CLZ27.NYM spread">
          <p className="text-sm text-[var(--text-secondary)]">
            Not charted: there is no futures data source in the lakehouse yet, so this
            spread has no verified prices behind it. It is shown here as a named gap
            rather than a fabricated series.
          </p>
        </Card>
      )}
    </div>
  );
}
