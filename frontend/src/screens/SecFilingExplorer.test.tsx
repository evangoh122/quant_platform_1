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

  it('shows no-coverage message for ticker without processed filings', async () => {
    mockSecCoverage.mockResolvedValue({
      data: [
        { ticker: 'XYZ', cik: '1', n_filings: 0, n_chunks: 0, first_filed: null, last_filed: null },
      ],
      count: 1,
      status: 'ok',
    });
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'XYZ' },
            result: { rows: [{ error: 'no_coverage', ticker: 'XYZ' }] },
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
    const option = await screen.findByText('XYZ');
    fireEvent.mouseDown(option);

    await waitFor(() => {
      expect(screen.getByText(/No SEC filings have been processed for XYZ yet\./i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/No SEC filing sections found for this search/i)).not.toBeInTheDocument();
  });

  it('renders rows from search_sec_filings even when it is not the first tool call', async () => {
    mockSecCoverage.mockResolvedValue({
      data: [
        { ticker: 'AAPL', cik: '1', n_filings: 42, n_chunks: 500, first_filed: null, last_filed: '2025-09-30' },
      ],
      count: 1,
      status: 'ok',
    });
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'some_other_tool',
            arguments: { query: 'something' },
            result: { data: 'irrelevant' },
            ok: true,
          },
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'AAPL' },
            result: { rows: [{ chunk_text: 'iPhone revenue growth', section: 'MD&A' }] },
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
    const option = await screen.findByText('AAPL');
    fireEvent.mouseDown(option);

    await waitFor(() => {
      expect(screen.getByText(/iPhone revenue growth/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/MD&A/i)).toBeInTheDocument();
  });

  it('shows retrieval_unavailable error state with retry button', async () => {
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
            result: {
              rows: [
                {
                  error: 'retrieval_unavailable',
                  message: 'SEC filing corpus could not be loaded. Check Delta table connectivity.',
                  ticker: 'NVDA',
                },
              ],
            },
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
      expect(screen.getByText(/SEC filing corpus could not be loaded/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Retry/i)).toBeInTheDocument();
    expect(screen.queryByText(/No SEC filing sections found/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/No SEC filings have been processed/i)).not.toBeInTheDocument();
  });

  it('retrieval_unavailable retry triggers re-fetch', async () => {
    mockSecCoverage.mockResolvedValue({
      data: [
        { ticker: 'NVDA', cik: '1', n_filings: 20, n_chunks: 200, first_filed: null, last_filed: '2025-09-30' },
      ],
      count: 1,
      status: 'ok',
    });
    mockChat
      .mockResolvedValueOnce(
        mockChatResponse({
          tool_calls: [
            {
              name: 'search_sec_filings',
              arguments: { symbol: 'NVDA' },
              result: {
                rows: [
                  {
                    error: 'retrieval_unavailable',
                    message: 'SEC filing corpus could not be loaded.',
                    ticker: 'NVDA',
                  },
                ],
              },
              ok: true,
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockChatResponse({
          tool_calls: [
            {
              name: 'search_sec_filings',
              arguments: { symbol: 'NVDA' },
              result: { rows: [{ chunk_text: 'GPU revenue', section: 'MD&A' }] },
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
      expect(screen.getByText(/Retry/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/Retry/i));

    await waitFor(() => {
      expect(screen.getByText(/GPU revenue/i)).toBeInTheDocument();
    });
  });

  it('shows generic error state for unknown error shapes', async () => {
    mockSecCoverage.mockResolvedValue({
      data: [
        { ticker: 'AAPL', cik: '1', n_filings: 42, n_chunks: 500, first_filed: null, last_filed: '2025-09-30' },
      ],
      count: 1,
      status: 'ok',
    });
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'AAPL' },
            result: {
              rows: [{ error: 'rate_limited', message: 'Too many requests. Try again later.' }],
            },
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
    const option = await screen.findByText('AAPL');
    fireEvent.mouseDown(option);

    await waitFor(() => {
      expect(screen.getByText(/Too many requests/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/No SEC filing sections found/i)).not.toBeInTheDocument();
  });

  it('unknown error without message falls back to error code', async () => {
    mockSecCoverage.mockResolvedValue({
      data: [
        { ticker: 'AAPL', cik: '1', n_filings: 42, n_chunks: 500, first_filed: null, last_filed: '2025-09-30' },
      ],
      count: 1,
      status: 'ok',
    });
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'AAPL' },
            result: { rows: [{ error: 'something_broke' }] },
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
    const option = await screen.findByText('AAPL');
    fireEvent.mouseDown(option);

    await waitFor(() => {
      expect(screen.getByText(/something_broke/i)).toBeInTheDocument();
    });
  });

  it('stale response from A is discarded when B is selected after A', async () => {
    mockSecCoverage.mockResolvedValue({
      data: [
        { ticker: 'AAPL', cik: '1', n_filings: 42, n_chunks: 500, first_filed: null, last_filed: '2025-09-30' },
        { ticker: 'NVDA', cik: '2', n_filings: 20, n_chunks: 200, first_filed: null, last_filed: '2025-09-30' },
      ],
      count: 2,
      status: 'ok',
    });

    let resolveA: (v: unknown) => void;
    const promiseA = new Promise((r) => {
      resolveA = r;
    });
    let resolveB: (v: unknown) => void;
    const promiseB = new Promise((r) => {
      resolveB = r;
    });

    mockChat.mockImplementation((msg: string) => {
      if (msg.includes('AAPL')) return promiseA;
      return promiseB;
    });

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/2 equities/i)).toBeInTheDocument();
    });

    const input = screen.getByRole('combobox');

    // Select AAPL
    fireEvent.focus(input);
    const optionA = await screen.findByText('AAPL');
    fireEvent.mouseDown(optionA);

    // Wait for AAPL to be selected (loading state shown)
    await waitFor(() => {
      expect(input).toHaveValue('AAPL');
    });

    // Clear the input and re-open dropdown to find NVDA
    const clearBtn = screen.getByLabelText('Clear selection');
    fireEvent.click(clearBtn);
    fireEvent.focus(input);

    const optionB = await screen.findByText('NVDA');
    fireEvent.mouseDown(optionB);

    // Resolve B first (this is the current selection)
    resolveB!(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'NVDA' },
            result: { rows: [{ chunk_text: 'GPU revenue', section: 'MD&A' }] },
            ok: true,
          },
        ],
      }),
    );

    await waitFor(() => {
      expect(screen.getByText(/GPU revenue/i)).toBeInTheDocument();
    });

    // Now resolve A (stale — should be discarded)
    resolveA!(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'AAPL' },
            result: { rows: [{ chunk_text: 'iPhone revenue', section: 'Products' }] },
            ok: true,
          },
        ],
      }),
    );

    // B's results should still be shown, not A's
    await waitFor(() => {
      expect(screen.getByText(/GPU revenue/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/iPhone revenue/i)).not.toBeInTheDocument();
  });

  it('shows error state when secTool result has error without rows', async () => {
    mockSecCoverage.mockResolvedValue({
      data: [
        { ticker: 'AAPL', cik: '1', n_filings: 42, n_chunks: 500, first_filed: null, last_filed: '2025-09-30' },
      ],
      count: 1,
      status: 'ok',
    });
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'AAPL' },
            result: { error: 'execution_failed' },
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
    const option = await screen.findByText('AAPL');
    fireEvent.mouseDown(option);

    await waitFor(() => {
      expect(screen.getByText(/execution_failed/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/No SEC filing sections found/i)).not.toBeInTheDocument();
  });

  it('clear button invalidates in-flight request', async () => {
    mockSecCoverage.mockResolvedValue({
      data: [
        { ticker: 'AAPL', cik: '1', n_filings: 42, n_chunks: 500, first_filed: null, last_filed: '2025-09-30' },
      ],
      count: 1,
      status: 'ok',
    });

    let resolveA: (v: unknown) => void;
    const promiseA = new Promise((r) => {
      resolveA = r;
    });
    mockChat.mockReturnValue(promiseA);

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/1 equity/i)).toBeInTheDocument();
    });

    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    const option = await screen.findByText('AAPL');
    fireEvent.mouseDown(option);

    await waitFor(() => {
      expect(input).toHaveValue('AAPL');
    });

    const clearBtn = screen.getByLabelText('Clear selection');
    fireEvent.click(clearBtn);

    // After clear: input is empty, empty state shown
    await waitFor(() => {
      expect(input).toHaveValue('');
    });
    expect(screen.getByText(/Select a ticker/i)).toBeInTheDocument();

    // Now resolve the old request — it should be discarded
    resolveA!(
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

    // Stale result must not appear
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/iPhone revenue/i)).not.toBeInTheDocument();
  });

  it('editing ticker input invalidates in-flight request', async () => {
    mockSecCoverage.mockResolvedValue({
      data: [
        { ticker: 'AAPL', cik: '1', n_filings: 42, n_chunks: 500, first_filed: null, last_filed: '2025-09-30' },
        { ticker: 'NVDA', cik: '2', n_filings: 20, n_chunks: 200, first_filed: null, last_filed: '2025-09-30' },
      ],
      count: 2,
      status: 'ok',
    });

    let resolveA: (v: unknown) => void;
    const promiseA = new Promise((r) => {
      resolveA = r;
    });
    mockChat.mockReturnValue(promiseA);

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/2 equities/i)).toBeInTheDocument();
    });

    const input = screen.getByRole('combobox');

    // Select AAPL
    fireEvent.focus(input);
    const optionA = await screen.findByText('AAPL');
    fireEvent.mouseDown(optionA);

    await waitFor(() => {
      expect(input).toHaveValue('AAPL');
    });

    // Edit the input (simulate user typing) — should invalidate the request
    fireEvent.change(input, { target: { value: 'N' } });

    // After edit: selected is cleared, stale result should not render
    await waitFor(() => {
      expect(input).toHaveValue('N');
    });

    // Resolve the old request — it should be discarded
    resolveA!(
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

    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/iPhone revenue/i)).not.toBeInTheDocument();
  });
});