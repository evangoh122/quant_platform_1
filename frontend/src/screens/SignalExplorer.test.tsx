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
  ],
  count: 2,
  empty: false,
  source: 'gold_trading_signals',
  freshness: { state: 'fresh', table: 'gold_trading_signals', detail: '2 rows' },
};

const mockEmptyResponse = {
  data: [],
  count: 0,
  empty: true,
  source: 'gold_trading_signals',
  freshness: { state: 'empty', table: 'gold_trading_signals', detail: 'no_signals_published' },
};

describe('SignalExplorer', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows baseline disclaimer with no edge claimed when signals are loaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockSignalsResponse),
    }));

    render(<SignalExplorer />);

    await waitFor(() => {
      expect(screen.getByText(/no validated trading edge claimed/)).toBeInTheDocument();
    });

    expect(screen.getByText(/Baseline demonstration/)).toBeInTheDocument();
    expect(screen.getAllByText(/baseline-logreg-v1-1d/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/1d/).length).toBeGreaterThanOrEqual(1);

    const disclaimer = screen.getByText(/Baseline demonstration/).closest('div')!;
    expect(disclaimer.textContent).not.toMatch(/\bAUC\b/i);
    expect(disclaimer.textContent).not.toMatch(/baseline-logreg-v0/);
  });

  it('shows baseline disclaimer with no edge claimed in empty state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockEmptyResponse),
    }));

    render(<SignalExplorer />);

    await waitFor(() => {
      expect(screen.getByText(/no validated trading edge claimed/)).toBeInTheDocument();
    });

    expect(screen.getByText(/Baseline demonstration/)).toBeInTheDocument();

    const disclaimer = screen.getByText(/Baseline demonstration/).closest('div')!;
    expect(disclaimer.textContent).not.toMatch(/\bAUC\b/i);
    expect(disclaimer.textContent).not.toMatch(/baseline-logreg-v\d/);
  });

  it('shows baseline disclaimer with no edge claimed in error state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    }));

    render(<SignalExplorer />);

    await waitFor(() => {
      expect(screen.getByText(/no validated trading edge claimed/)).toBeInTheDocument();
    });

    expect(screen.getByText(/Baseline demonstration/)).toBeInTheDocument();

    const disclaimer = screen.getByText(/Baseline demonstration/).closest('div')!;
    expect(disclaimer.textContent).not.toMatch(/\bAUC\b/i);
    expect(disclaimer.textContent).not.toMatch(/baseline-logreg-v\d/);
  });

  it('renders model_version from signal rows when present', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockSignalsResponse),
    }));

    render(<SignalExplorer />);

    await waitFor(() => {
      expect(screen.getAllByText(/baseline-logreg-v1-1d/).length).toBeGreaterThanOrEqual(1);
    });
  });
});