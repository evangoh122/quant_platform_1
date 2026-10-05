import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SecFilingExplorer } from './SecFilingExplorer';

const mockChat = vi.fn();
const mockSecCoverage = vi.fn();

vi.mock('../api/client', () => ({
  api: {
    chat: (...args: unknown[]) => mockChat(...args),
    secCoverage: (...args: unknown[]) => mockSecCoverage(...args),
  },
}));

function mockChatResponse(overrides: Record<string, unknown>) {
  return {
    reply: '',
    tool_calls: [],
    sources: [],
    available: true,
    empty: false,
    ...overrides,
  };
}

function makeCoverageData(count: number) {
  const data = Array.from({ length: count }, (_, i) => ({
    ticker: `T${String(i + 1).padStart(3, '0')}`,
    cik: `000${String(i + 1).padStart(7, '0')}`,
    n_filings: 10 + i,
    n_chunks: 100 + i * 10,
    first_filed: '2024-01-15',
    last_filed: '2025-09-30',
  }));
  return { data, count, status: 'ok' as const };
}

describe('SecFilingExplorer', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // Default: coverage returns a small set
    mockSecCoverage.mockResolvedValue(makeCoverageData(5));
  });

  it('shows loading state while coverage is fetching', () => {
    mockSecCoverage.mockReturnValue(new Promise(() => {})); // never resolves
    render(<SecFilingExplorer />);
    expect(screen.getByText(/Loading equities/i)).toBeInTheDocument();
  });

  it('shows equity count after coverage loads', async () => {
    mockSecCoverage.mockResolvedValue(makeCoverageData(228));
    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/228 equities with SEC filings/i)).toBeInTheDocument();
    });
  });

  it('lists all tickers from coverage response', async () => {
    mockSecCoverage.mockResolvedValue(makeCoverageData(5));
    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/5 equities/i)).toBeInTheDocument();
    });
    // Open the dropdown
    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(5);
  });

  it('filters tickers on typing', async () => {
    mockSecCoverage.mockResolvedValue(
      makeCoverageData(0),
    );
    // Custom data with known tickers
    mockSecCoverage.mockResolvedValue({
      data: [
        { ticker: 'AAPL', cik: '1', n_filings: 42, n_chunks: 500, first_filed: null, last_filed: '2025-09-30' },
        { ticker: 'AMZN', cik: '2', n_filings: 30, n_chunks: 300, first_filed: null, last_filed: '2025-08-15' },
        { ticker: 'MSFT', cik: '3', n_filings: 35, n_chunks: 400, first_filed: null, last_filed: '2025-07-20' },
      ],
      count: 3,
      status: 'ok',
    });

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/3 equities/i)).toBeInTheDocument();
    });

    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'AA' } });

    await waitFor(() => {
      const options = screen.getAllByRole('option');
      expect(options).toHaveLength(1);
      expect(within(options[0]).getByText('AAPL')).toBeInTheDocument();
    });
  });

  it('choosing a ticker calls api.chat with that ticker', async () => {
    mockSecCoverage.mockResolvedValue({
      data: [
        { ticker: 'NVDA', cik: '1', n_filings: 20, n_chunks: 200, first_filed: null, last_filed: '2025-09-30' },
      ],
      count: 1,
      status: 'ok',
    });
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'NVDA' },
            result: { rows: [{ chunk_text: 'GPU revenue growth', section: 'MD&A' }] },
            ok: true,
          },
        ],
      }),
    );

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/1 equity/i)).toBeInTheDocument();
    });

    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    const option = await screen.findByText('NVDA');
    fireEvent.mouseDown(option);

    await waitFor(() => {
      expect(mockChat).toHaveBeenCalledWith('search SEC filings for NVDA');
    });
  });

  it('coverage failure falls back to free-text input with notice', async () => {
    mockSecCoverage.mockRejectedValue(new Error('Network error'));

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/Equity coverage data is unavailable/i)).toBeInTheDocument();
    });
    // Should show the free-text input instead of combobox
    expect(screen.getByPlaceholderText(/Search filings for a symbol/i)).toBeInTheDocument();
    // Should NOT show combobox
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('coverage unavailable status falls back to free-text input', async () => {
    mockSecCoverage.mockResolvedValue({ data: [], count: 0, status: 'unavailable' });

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/Equity coverage data is unavailable/i)).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText(/Search filings for a symbol/i)).toBeInTheDocument();
  });

  it('fallback free-text input still works for searching', async () => {
    mockSecCoverage.mockRejectedValue(new Error('fail'));
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'AAPL' },
            result: { rows: [{ chunk_text: 'iPhone revenue', section: 'MD&A' }] },
            ok: true,
          },
        ],
      }),
    );

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText(/Search filings/i), { target: { value: 'AAPL' } });
    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      expect(mockChat).toHaveBeenCalledWith('search SEC filings for AAPL');
    });
  });

  it('selector shows filing count and last filed date per option', async () => {
    mockSecCoverage.mockResolvedValue({
      data: [
        { ticker: 'AAPL', cik: '1', n_filings: 42, n_chunks: 500, first_filed: null, last_filed: '2025-09-30' },
      ],
      count: 1,
      status: 'ok',
    });

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/1 equity/i)).toBeInTheDocument();
    });

    const input = screen.getByRole('combobox');
    fireEvent.focus(input);

    await waitFor(() => {
      expect(screen.getByText(/42 filings/)).toBeInTheDocument();
      expect(screen.getByText(/Sep 30, 2025/)).toBeInTheDocument();
    });
  });

  it('selector caps the list (mutation: endpoint returns many items)', async () => {
    // Even with 228 items, the selector should render without error
    mockSecCoverage.mockResolvedValue(makeCoverageData(228));

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/228 equities/i)).toBeInTheDocument();
    });

    const input = screen.getByRole('combobox');
    fireEvent.focus(input);

    await waitFor(() => {
      const options = screen.getAllByRole('option');
      expect(options).toHaveLength(228);
    });
  });

  it('shows initial state before any selection', async () => {
    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/Select a ticker to see its SEC filing sections/i)).toBeInTheDocument();
    });
  });
});