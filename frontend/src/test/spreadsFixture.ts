import type { MarketSpreadsResponse, SpreadChart, SpreadPoint, SpreadSeries } from '../api/types';

/**
 * A populated `/api/spreads` payload for the shell-level design guards.
 *
 * The guards in `layout-overflow.test.tsx` and `brand-and-eyebrows.test.tsx`
 * render the real screen, so this fixture has to produce real charts: five
 * charts with at least two aligned dates each, the yield chart carrying the
 * two-leg series and the API-computed 10s2s tile. It mirrors the live route's
 * shape (`api/schemas.py MarketSpreadsResponse`) without asserting any values
 * the backend computes.
 */
const DATES = ['2026-09-29', '2026-09-30', '2026-10-01'] as const;

const OHLCV_FRESH = {
  state: 'fresh' as const,
  table: 'silver_ohlcv_day_adjusted',
  detail: '3 rows',
};

const FED_FRESH = {
  state: 'fresh' as const,
  table: 'bronze_fed_series',
  detail: '3 rows',
};

function series(
  key: string,
  label: string,
  values: readonly [number, number, number],
  windowPctChange: number | null,
): SpreadSeries {
  return {
    key,
    label,
    points: DATES.map((date, index): SpreadPoint => [date, values[index]]),
    latest_value: values[values.length - 1],
    latest_date: DATES[DATES.length - 1],
    window_pct_change: windowPctChange,
  };
}

function chart(overrides: Partial<SpreadChart> & Pick<SpreadChart, 'chart_id' | 'title'>): SpreadChart {
  return {
    subtitle: 'relative performance, rebased to 100, price return (splits adjusted, dividends not)',
    kind: 'index',
    unit: 'index',
    source: 'silver_ohlcv_day_adjusted',
    freshness: OHLCV_FRESH,
    empty: false,
    series: [],
    first_common_date: DATES[0],
    dropped_dates: 0,
    as_of: DATES[DATES.length - 1],
    tile: null,
    caption: '',
    ...overrides,
  };
}

export const populatedSpreadsResponse: MarketSpreadsResponse = {
  days: 1000,
  window_start: '2026-09-29',
  window_end: '2026-10-01',
  charts: [
    chart({
      chart_id: 'uso_price',
      title: 'USO — split-adjusted close',
      subtitle: 'split-adjusted close, dividends not',
      kind: 'price',
      unit: 'USD',
      series: [series('USO', 'USO close', [70.12, 71.4, 72.05], 2.75)],
      caption: 'Split-adjusted close 72.05 USD on 2026-10-01. Window change +2.75%.',
    }),
    chart({
      chart_id: 'treasury_yields',
      title: 'US 10Y and 2Y Treasury yields',
      subtitle: 'constant-maturity yields, Federal Reserve H.15',
      kind: 'yield',
      unit: '%',
      source: 'bronze_fed_series',
      freshness: FED_FRESH,
      series: [
        series('DGS10', '10Y Treasury yield (DGS10)', [4.12, 4.18, 4.21], null),
        series('DGS2', '2Y Treasury yield (DGS2)', [4.52, 4.48, 4.44], null),
      ],
      dropped_dates: 1,
      tile: {
        label: '10s2s',
        value: -0.23,
        as_of: DATES[DATES.length - 1],
        unit: 'pp',
        points: DATES.map(
          (date, index): SpreadPoint => [date, [4.12, 4.18, 4.21][index] - [4.52, 4.48, 4.44][index]],
        ),
      },
      caption: '10s2s = DGS10 − DGS2 on 2 common dates; latest -0.23 pp on 2026-10-01.',
    }),
    chart({
      chart_id: 'rsp_spy',
      title: 'RSP / SPY relative performance',
      series: [series('RSP/SPY', 'RSP / SPY (rebased 100)', [100, 100.8, 101.6], 1.6)],
      caption: 'RSP outperformed SPY by 1.60% over the window.',
    }),
    chart({
      chart_id: 'mags_soxx',
      title: 'MAGS / SOXX relative performance',
      series: [series('MAGS/SOXX', 'MAGS / SOXX (rebased 100)', [100, 99.4, 98.9], -1.1)],
      caption: 'SOXX outperformed MAGS by 1.10% over the window.',
    }),
    chart({
      chart_id: 'mags_smh',
      title: 'MAGS / SMH relative performance',
      series: [series('MAGS/SMH', 'MAGS / SMH (rebased 100)', [100, 100.2, 100.5], 0.5)],
      caption: 'MAGS outperformed SMH by 0.50% over the window.',
    }),
  ],
};

export default populatedSpreadsResponse;
