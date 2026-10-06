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
    localStorage.clear();
    window.history.replaceState(null, '', window.location.pathname);
    mockSecCoverage.mockResolvedValue(makeCoverageData(5));
  });

  it('shows loading state while coverage is fetching', () => {
    mockSecCoverage.mockReturnValue(new Promise(() => {}));
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
    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(5);
  });

  it('filters tickers on typing', async () => {
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
      expect(options[0]).toHaveTextContent('AAPL');
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
    const option = screen.getByRole('listbox').querySelector('[role="option"]');
    expect(option).toBeTruthy();
    fireEvent.mouseDown(option!);

    await waitFor(() => {
      expect(mockChat).toHaveBeenCalledWith('search SEC filings for NVDA');
    });
  });

  it('coverage failure falls back to SymbolPicker with sec list', async () => {
    mockSecCoverage.mockRejectedValue(new Error('Network error'));

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/Equity coverage data is unavailable/i)).toBeInTheDocument();
    });
    // Should show SymbolPicker (combobox) even in fallback
    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(screen.getByText('Equity')).toBeInTheDocument();
  });

  it('coverage unavailable status falls back to SymbolPicker with sec list', async () => {
    mockSecCoverage.mockResolvedValue({ data: [], count: 0, status: 'unavailable' });

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/Equity coverage data is unavailable/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('fallback SymbolPicker allows searching by typing', async () => {
    mockSecCoverage.mockRejectedValue(new Error('fail'));
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'AMD' },
            result: { rows: [{ chunk_text: 'AMD revenue', section: 'MD&A' }] },
            ok: true,
          },
        ],
      }),
    );

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
    });

    // Type in the SymbolPicker combobox and select from dropdown
    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'AMD' } });

    await waitFor(() => {
      const options = screen.getAllByRole('option');
      expect(options.length).toBeGreaterThan(0);
    });
    const option = screen.getAllByRole('option')[0];
    fireEvent.mouseDown(option);

    await waitFor(() => {
      expect(mockChat).toHaveBeenCalledWith('search SEC filings for AMD');
    });
  });

  it('fallback SymbolPicker allows submitting a typed ticker not in the list', async () => {
    mockSecCoverage.mockRejectedValue(new Error('fail'));
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'TSLA' },
            result: { rows: [{ chunk_text: 'Tesla revenue', section: 'MD&A' }] },
            ok: true,
          },
        ],
      }),
    );

    render(<SecFilingExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
    });

    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'TSLA' } });

    // TSLA is not in the sec list, but passes ticker format — should show submit option
    await waitFor(() => {
      expect(screen.getByText(/Submit TSLA/)).toBeInTheDocument();
    });

    fireEvent.mouseDown(screen.getByText(/Submit TSLA/));

    await waitFor(() => {
      expect(mockChat).toHaveBeenCalledWith('search SEC filings for TSLA');
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
    const option = screen.getByRole('listbox').querySelector('[role="option"]');
    expect(option).toBeTruthy();
    fireEvent.mouseDown(option!);

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
    const option = screen.getByRole('listbox').querySelector('[role="option"]');
    expect(option).toBeTruthy();
    fireEvent.mouseDown(option!);

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
    const option = screen.getByRole('listbox').querySelector('[role="option"]');
    expect(option).toBeTruthy();
    fireEvent.mouseDown(option!);

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
    const option = screen.getByRole('listbox').querySelector('[role="option"]');
    expect(option).toBeTruthy();
    fireEvent.mouseDown(option!);

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
    const option = screen.getByRole('listbox').querySelector('[role="option"]');
    expect(option).toBeTruthy();
    fireEvent.mouseDown(option!);

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
    const option = screen.getByRole('listbox').querySelector('[role="option"]');
    expect(option).toBeTruthy();
    fireEvent.mouseDown(option!);

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

    // Select AAPL from dropdown
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'AAPL' } });
    await waitFor(() => {
      const opts = screen.getAllByRole('option');
      expect(opts.length).toBeGreaterThan(0);
    });
    const optionA = screen.getAllByRole('option')[0];
    fireEvent.mouseDown(optionA);

    await waitFor(() => {
      expect(input).toHaveValue('AAPL');
    });

    // Clear and select NVDA
    const clearBtn = screen.getByLabelText('Clear');
    fireEvent.click(clearBtn);
    fireEvent.change(input, { target: { value: 'NVDA' } });
    await waitFor(() => {
      const opts = screen.getAllByRole('option');
      expect(opts.length).toBeGreaterThan(0);
    });
    const optionB = screen.getAllByRole('option')[0];
    fireEvent.mouseDown(optionB);

    // Resolve B first
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

    // Resolve A (stale)
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
    const option = screen.getByRole('listbox').querySelector('[role="option"]');
    expect(option).toBeTruthy();
    fireEvent.mouseDown(option!);

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
    const option = screen.getByRole('listbox').querySelector('[role="option"]');
    expect(option).toBeTruthy();
    fireEvent.mouseDown(option!);

    await waitFor(() => {
      expect(input).toHaveValue('AAPL');
    });

    const clearBtn = screen.getByLabelText('Clear');
    fireEvent.click(clearBtn);

    await waitFor(() => {
      expect(input).toHaveValue('');
    });
    expect(screen.getByText(/Select a ticker/i)).toBeInTheDocument();

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