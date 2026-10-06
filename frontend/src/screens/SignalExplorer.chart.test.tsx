import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SignalExplorer } from './SignalExplorer';

const mockSignalsResponse = {
  data: [
    {
      signal_id: 'sig-001',
      symbol: 'AAPL',
      direction: 'LONG',
      probability: 0.612,
      prediction_ts: '2026-10-05T14:30:00Z',
      model_version: 'baseline-logreg-v1-1d',
      horizon: '1d',
      status: 'active',
      feature_snapshot_id: 'snap-001',
    },
    {
      signal_id: 'sig-002',
      symbol: 'MSFT',
      direction: 'SHORT',
      probability: 0.583,
      prediction_ts: '2026-10-05T14:30:00Z',
      model_version: 'baseline-logreg-v1-1d',
      horizon: '1d',
      status: 'active',
      feature_snapshot_id: 'snap-002',
    },
    {
      signal_id: 'sig-003',
      symbol: 'NVDA',
      direction: 'LONG',
      probability: 0.721,
      prediction_ts: '2026-10-05T14:30:00Z',
      model_version: 'baseline-logreg-v1-1d',
      horizon: '1d',
      status: 'active',
      feature_snapshot_id: 'snap-003',
    },
  ],
  count: 3,
  empty: false,
  source: 'gold_trading_signals',
  freshness: { state: 'fresh', table: 'gold_trading_signals', detail: '3 rows' },
};

const emptySignalsResponse = {
  data: [],
  count: 0,
  empty: true,
  source: 'gold_trading_signals',
  freshness: { state: 'empty', table: 'gold_trading_signals', detail: 'no_signals_published' },
};

describe('SignalExplorer conviction chart', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders bars sorted by probability descending', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockSignalsResponse),
    }));

    render(<SignalExplorer />);

    await waitFor(() => {
      expect(screen.getAllByText(/Baseline model probability/).length).toBeGreaterThanOrEqual(1);
    });

    const chart = screen.getByRole('img', { name: /signal conviction ranking/i });
    expect(chart).toBeInTheDocument();

    const rects = chart.querySelectorAll('rect[fill]');
    expect(rects.length).toBe(3);

    // Bars should be sorted by probability descending: NVDA (0.721) > AAPL (0.612) > MSFT (0.583)
    const widths = Array.from(rects).map((r) => parseFloat(r.getAttribute('width') || '0'));
    expect(widths[0]).toBeGreaterThan(widths[1]);
    expect(widths[1]).toBeGreaterThan(widths[2]);
  });

  it('contains text "Baseline model probability" and not "expected return"', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockSignalsResponse),
    }));

    render(<SignalExplorer />);

    await waitFor(() => {
      expect(screen.getAllByText(/Baseline model probability/).length).toBeGreaterThanOrEqual(1);
    });

    // "expected return" should NOT appear anywhere
    expect(screen.queryByText(/expected return/i)).not.toBeInTheDocument();

    // The table header should say "Baseline model probability" (appears in both chart table and main table)
    const headers = screen.getAllByText(/Baseline model probability/);
    expect(headers.length).toBeGreaterThanOrEqual(1);
  });

  it('shows model_version and horizon in chart caption', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockSignalsResponse),
    }));

    render(<SignalExplorer />);

    await waitFor(() => {
      expect(screen.getAllByText(/baseline-logreg-v1-1d/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows empty state when no signals', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(emptySignalsResponse),
    }));

    render(<SignalExplorer />);

    await waitFor(() => {
      expect(screen.getAllByText(/No signals published yet/).length).toBeGreaterThanOrEqual(1);
    });

    // "expected return" should NOT appear anywhere
    expect(screen.queryByText(/expected return/i)).not.toBeInTheDocument();
  });

  it('shows error state on API failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    }));

    render(<SignalExplorer />);

    await waitFor(() => {
      expect(screen.getByText(/Something went wrong/)).toBeInTheDocument();
    });
  });
});