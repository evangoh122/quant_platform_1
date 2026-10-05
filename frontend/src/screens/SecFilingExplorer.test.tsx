import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SecFilingExplorer } from './SecFilingExplorer';

const mockChat = vi.fn();

vi.mock('../api/client', () => ({
  api: { chat: (...args: unknown[]) => mockChat(...args) },
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

describe('SecFilingExplorer', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows initial state before any search', () => {
    render(<SecFilingExplorer />);
    expect(screen.getByText(/Search a ticker to see its SEC filing sections/i)).toBeInTheDocument();
  });

  it('shows no-coverage message for ticker without processed filings', async () => {
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'NVDA' },
            result: { rows: [{ error: 'no_coverage', ticker: 'NVDA' }] },
            ok: true,
          },
        ],
      }),
    );

    render(<SecFilingExplorer />);
    fireEvent.change(screen.getByPlaceholderText(/Search filings/i), { target: { value: 'NVDA' } });
    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      expect(screen.getByText(/No SEC filings have been processed for NVDA yet/i)).toBeInTheDocument();
    });
  });

  it('renders rows from a successful search', async () => {
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'AAPL' },
            result: {
              rows: [
                { chunk_text: 'Risk factors include competition', section: 'Risk Factors', edgar_url: 'https://example.com' },
                { chunk_text: 'Revenue recognition policies', section: 'MD&A' },
              ],
            },
            ok: true,
          },
        ],
      }),
    );

    render(<SecFilingExplorer />);
    fireEvent.change(screen.getByPlaceholderText(/Search filings/i), { target: { value: 'AAPL' } });
    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      expect(screen.getByText(/Risk factors include competition/i)).toBeInTheDocument();
      expect(screen.getByText(/Revenue recognition policies/i)).toBeInTheDocument();
      expect(screen.getByText('Risk Factors')).toBeInTheDocument();
      expect(screen.getByText('MD&A')).toBeInTheDocument();
    });
  });

  it('shows empty message when search returns zero rows', async () => {
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'XYZ' },
            result: { rows: [] },
            ok: true,
          },
        ],
      }),
    );

    render(<SecFilingExplorer />);
    fireEvent.change(screen.getByPlaceholderText(/Search filings/i), { target: { value: 'XYZ' } });
    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      expect(screen.getByText(/No SEC filing sections found for this search/i)).toBeInTheDocument();
    });
  });

  it('never shows the old silver_sec_sections empty string', async () => {
    mockChat.mockResolvedValue(
      mockChatResponse({
        tool_calls: [
          {
            name: 'search_sec_filings',
            arguments: { symbol: 'XYZ' },
            result: { rows: [] },
            ok: true,
          },
        ],
      }),
    );

    render(<SecFilingExplorer />);
    fireEvent.change(screen.getByPlaceholderText(/Search filings/i), { target: { value: 'XYZ' } });
    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      expect(screen.queryByText(/silver_sec_sections is empty/i)).not.toBeInTheDocument();
    });
  });

  it('shows error state when api.chat throws', async () => {
    mockChat.mockRejectedValue(new Error('Network failure'));

    render(<SecFilingExplorer />);
    fireEvent.change(screen.getByPlaceholderText(/Search filings/i), { target: { value: 'AAPL' } });
    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      expect(screen.getByText(/Network failure/i)).toBeInTheDocument();
    });
  });
});