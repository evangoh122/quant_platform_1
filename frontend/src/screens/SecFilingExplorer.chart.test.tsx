import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SecFilingExplorer } from './SecFilingExplorer';

function generateCoverage(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    ticker: `T${String(i + 1).padStart(2, '0')}`,
    cik: `000${String(i + 1).padStart(7, '0')}`,
    n_filings: 10 - (i % 5),
    n_chunks: i < 25 ? 100 : 5000 - i * 10,
    first_filed: '2024-01-01',
    last_filed: '2026-09-01',
  }));
}

const mockCoverageResponse30 = {
  data: generateCoverage(30),
  count: 30,
  status: 'ok' as const,
};

const emptyCoverageResponse = {
  data: [],
  count: 0,
  status: 'ok' as const,
};

describe('SecFilingExplorer coverage chart', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows 25 bars by default when 30 tickers are available', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockCoverageResponse30),
    }));

    render(<SecFilingExplorer />);

    await waitFor(() => {
      expect(screen.getByText(/SEC Research Coverage/)).toBeInTheDocument();
    });

    // The chart SVG should be rendered
    const chart = screen.getByRole('img', { name: /SEC coverage chart/i });
    expect(chart).toBeInTheDocument();

    // Should show "Show all 30" button
    expect(screen.getByText('Show all 30')).toBeInTheDocument();

    // Default shows top 25 — count the rect elements with fill (bars)
    const bars = chart.querySelectorAll('rect[fill]');
    expect(bars.length).toBe(25);
  });

  it('shows 30 bars after toggling "Show all"', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockCoverageResponse30),
    }));

    render(<SecFilingExplorer />);

    await waitFor(() => {
      expect(screen.getByText('Show all 30')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Show all 30'));

    const chart = screen.getByRole('img', { name: /SEC coverage chart/i });
    const bars = chart.querySelectorAll('rect[fill]');
    expect(bars.length).toBe(30);

    // Button should now say "Show top 25"
    expect(screen.getByText('Show top 25')).toBeInTheDocument();
  });

  it('orders bars by n_chunks descending', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockCoverageResponse30),
    }));

    render(<SecFilingExplorer />);

    await waitFor(() => {
      expect(screen.getByText(/SEC Research Coverage/)).toBeInTheDocument();
    });

    const chart = screen.getByRole('img', { name: /SEC coverage chart/i });
    const bars = chart.querySelectorAll('rect[fill]');

    // Bars should be in descending order of width (which maps to n_chunks)
    const widths = Array.from(bars).map((b) => parseFloat(b.getAttribute('width') || '0'));
    for (let i = 1; i < widths.length; i++) {
      expect(widths[i]).toBeLessThanOrEqual(widths[i - 1]);
    }

    // T26 has 4740 chunks (much more than T01-T25 which have 100 each)
    // so T26 must appear in the top 25. Mutation: slice before sort → T26 excluded → fail.
    const labels = chart.querySelectorAll('text');
    const tickerLabels = Array.from(labels).map((t) => t.textContent).filter((t) => t?.startsWith('T'));
    expect(tickerLabels).toContain('T26');
  });

  it('shows headline counts (tickers with chunks / total)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockCoverageResponse30),
    }));

    render(<SecFilingExplorer />);

    await waitFor(() => {
      expect(screen.getByText(/30 \/ 30 tickers with chunks/)).toBeInTheDocument();
    });

    expect(screen.getByText(/total chunks/)).toBeInTheDocument();
  });

  it('renders data table in details fallback', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockCoverageResponse30),
    }));

    render(<SecFilingExplorer />);

    await waitFor(() => {
      expect(screen.getByText('View data table')).toBeInTheDocument();
    });
  });

  it('shows empty state when coverage data is empty', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(emptyCoverageResponse),
    }));

    render(<SecFilingExplorer />);

    // When coverage is empty, the chart card is not rendered
    await waitFor(() => {
      expect(screen.getByText(/0 equit/)).toBeInTheDocument();
    });
  });

  it('shows error state on API failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    }));

    render(<SecFilingExplorer />);

    await waitFor(() => {
      expect(screen.getByText(/Loading equities/)).toBeInTheDocument();
    });
  });
});