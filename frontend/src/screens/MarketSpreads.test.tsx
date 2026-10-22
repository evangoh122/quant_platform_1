import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MarketSpreads } from './MarketSpreads';
import type { MarketSpreadsResponse, SpreadChart, SpreadSeries } from '../api/types';

const FRESH = { state: 'fresh' as const, table: 'silver_ohlcv_day_adjusted', detail: '3 rows' };

function makeSeries(
  key: string,
  label: string,
  start: number,
  end: number,
  pct: number | null,
): SpreadSeries {
  return {
    key,
    label,
    points: [
      ['2024-01-02', start],
      ['2024-01-03', end],
    ],
    latest_value: end,
    latest_date: '2024-01-03',
    window_pct_change: pct,
  };
}

function makeChart(overrides: Partial<SpreadChart> & Pick<SpreadChart, 'chart_id' | 'title'>): SpreadChart {
  return {
    subtitle: 'relative performance, rebased to 100, price return (splits adjusted, dividends not)',
    kind: 'index',
    unit: 'index',
    source: 'silver_ohlcv_day_adjusted',
    freshness: FRESH,
    empty: false,
    series: [],
    first_common_date: '2024-01-02',
    dropped_dates: 0,
    as_of: '2024-01-03',
    tile: null,
    caption: '',
    ...overrides,
  };
}

function makeResponse(): MarketSpreadsResponse {
  return {
    days: 1000,
    window_start: '2024-01-02',
    window_end: '2026-10-01',
    charts: [
      makeChart({
        chart_id: 'uso_price',
        title: 'USO — split-adjusted close',
        kind: 'price',
        unit: 'USD',
        series: [makeSeries('USO', 'USO', 70, 77, 10)],
        caption: 'Split-adjusted close 77.00 USD on 2024-01-03. Window change +10.00%.',
      }),
      makeChart({
        chart_id: 'treasury_yields',
        title: 'US 10Y and 2Y Treasury yields',
        kind: 'yield',
        unit: '%',
        source: 'bronze_fed_series',
        freshness: { state: 'fresh', table: 'bronze_fed_series', detail: '6 rows' },
        series: [
          makeSeries('DGS10', '10Y Treasury yield (DGS10)', 4.1, 4.2, null),
          makeSeries('DGS2', '2Y Treasury yield (DGS2)', 4.5, 4.3, null),
        ],
        dropped_dates: 2,
        tile: {
          label: '10s2s',
          value: -0.1,
          as_of: '2024-01-03',
          unit: 'pp',
          points: [],
        },
        caption: '10s2s = DGS10 − DGS2 on 2 common dates; latest -0.10 pp on 2024-01-03.',
      }),
      makeChart({
        chart_id: 'rsp_spy',
        title: 'RSP / SPY relative performance',
        series: [makeSeries('RSP/SPY', 'RSP / SPY (rebased 100)', 100, 121, 21)],
        caption: 'RSP outperformed SPY by 21.00% over the window (price return, splits adjusted, dividends not).',
      }),
      makeChart({
        chart_id: 'mags_soxx',
        title: 'MAGS / SOXX relative performance',
        series: [makeSeries('MAGS/SOXX', 'MAGS / SOXX (rebased 100)', 100, 104, 4)],
        caption: 'MAGS outperformed SOXX by 4.00% over the window.',
      }),
      makeChart({
        chart_id: 'mags_smh',
        title: 'MAGS / SMH relative performance',
        series: [makeSeries('MAGS/SMH', 'MAGS / SMH (rebased 100)', 100, 99, -1)],
        caption: 'SMH outperformed MAGS by 1.00% over the window.',
      }),
    ],
  };
}

function stubFetch(body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(body) }),
  );
}

describe('MarketSpreads', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders five charts plus the static futures gap card', async () => {
    stubFetch(makeResponse());
    render(<MarketSpreads />);

    await waitFor(() => {
      expect(screen.getAllByRole('img')).toHaveLength(5);
    });

    expect(screen.getByRole('group', { name: 'Chart window' })).toBeInTheDocument();

    const charts = screen.getAllByRole('img');
    for (const chart of charts) {
      expect(chart.getAttribute('aria-label')).toBeTruthy();
    }
    expect(screen.getByRole('img', { name: /split-adjusted close chart/i })).toBeInTheDocument();
    expect(
      screen.getByRole('img', { name: /US 10Y and 2Y Treasury yields chart/i }),
    ).toBeInTheDocument();
    expect(screen.getByText('RSP / SPY relative performance')).toBeInTheDocument();
    expect(screen.getByText('MAGS / SOXX relative performance')).toBeInTheDocument();
    expect(screen.getByText('MAGS / SMH relative performance')).toBeInTheDocument();

    // 10s2s tile from the API, not recomputed in the browser.
    expect(screen.getByText('10s2s')).toBeInTheDocument();
    expect(screen.getByText('-0.10 pp')).toBeInTheDocument();
    expect(screen.getByText('as of 2024-01-03')).toBeInTheDocument();

    expect(screen.getByText(/2 dates missing in one leg/)).toBeInTheDocument();
    expect(screen.getByText(/RSP outperformed SPY by 21.00%/)).toBeInTheDocument();

    expect(
      screen.getByText(/no futures data source in the lakehouse yet/i),
    ).toBeInTheDocument();
  });

  it('exposes a visually hidden summary with latest value, change and as-of date', async () => {
    stubFetch(makeResponse());
    render(<MarketSpreads />);

    await waitFor(() => {
      expect(screen.getAllByRole('img')).toHaveLength(5);
    });

    expect(
      screen.getByText(/index 121\.00 \(100 = first common date 2024-01-02\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/window change \+21\.00%/)).toBeInTheDocument();
    expect(screen.getByText(/latest 77\.00 USD as of 2024-01-03/)).toBeInTheDocument();
  });

  it('renders a per-chart empty state without dropping the other charts', async () => {
    const response = makeResponse();
    response.charts[4] = makeChart({
      chart_id: 'mags_smh',
      title: 'MAGS / SMH relative performance',
      empty: true,
      series: [makeSeries('MAGS/SMH', 'MAGS / SMH (rebased 100)', 100, 100, null)],
      first_common_date: null,
    });
    stubFetch(response);
    render(<MarketSpreads />);

    await waitFor(() => {
      expect(screen.getByText('No data for this window')).toBeInTheDocument();
    });

    expect(screen.getAllByRole('img')).toHaveLength(4);
    expect(screen.getByText(/No usable values in this window/)).toBeInTheDocument();
    // Other charts still render.
    expect(screen.getByRole('img', { name: /RSP \/ SPY relative performance chart/i })).toBeInTheDocument();
  });

  it('shows an unavailable badge and message when a source degrades', async () => {
    const response = makeResponse();
    response.charts[1] = makeChart({
      chart_id: 'treasury_yields',
      title: 'US 10Y and 2Y Treasury yields',
      kind: 'yield',
      unit: '%',
      source: 'bronze_fed_series',
      freshness: { state: 'unavailable', table: 'bronze_fed_series', detail: 'delta read failed' },
      empty: true,
      series: [],
      tile: null,
    });
    stubFetch(response);
    render(<MarketSpreads />);

    await waitFor(() => {
      expect(screen.getByText(/bronze_fed_series is unavailable/)).toBeInTheDocument();
    });
    expect(screen.getByText('unavailable')).toBeInTheDocument();
    expect(screen.getAllByRole('img')).toHaveLength(4);
  });

  it('renders an error state and retries the request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));
    const user = userEvent.setup();
    render(<MarketSpreads />);

    await waitFor(() => {
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });
    expect(screen.getByText('network down')).toBeInTheDocument();

    const fetchMock = vi.mocked(fetch);
    const callsBefore = fetchMock.mock.calls.length;
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it('requests trading-day windows for every range button', async () => {
    stubFetch(makeResponse());
    const user = userEvent.setup();
    render(<MarketSpreads />);

    await waitFor(() => {
      expect(screen.getAllByRole('img')).toHaveLength(5);
    });

    const fetchMock = vi.mocked(fetch);
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/spreads?days=1000');
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');

    // The window is TRADING days, so 1M/3M/6M/All = 21/63/126/1000, never the
    // calendar-day values 30/90/180.
    const windows = [
      ['1M', 21],
      ['3M', 63],
      ['6M', 126],
      ['All', 1000],
    ] as const;

    for (const [label, days] of windows) {
      await user.click(screen.getByRole('button', { name: label }));

      await waitFor(() => {
        const urls = fetchMock.mock.calls.map((call) => String(call[0]));
        expect(urls.some((url) => url.includes(`/api/spreads?days=${days}`))).toBe(true);
      });
      expect(screen.getByRole('button', { name: label })).toHaveAttribute('aria-pressed', 'true');
      expect(screen.getByText(new RegExp(`last ${days} trading days`))).toBeInTheDocument();
      if (label === '1M') {
        expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute(
          'aria-pressed',
          'false',
        );
      }
    }

    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(urls.some((url) => /days=(30|90|180)\b/.test(url))).toBe(false);
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('uses evidence language only — no BUY/SELL strings', async () => {
    stubFetch(makeResponse());
    render(<MarketSpreads />);

    await waitFor(() => {
      expect(screen.getAllByRole('img')).toHaveLength(5);
    });

    expect(document.body.textContent ?? '').not.toMatch(/\b(BUY|SELL)\b/);
    expect(document.body.textContent ?? '').not.toMatch(/rich|cheap|signal score/i);
  });
});
