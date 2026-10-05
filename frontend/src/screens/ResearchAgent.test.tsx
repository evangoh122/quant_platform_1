import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ResearchAgent } from './ResearchAgent';

const mockChatResponse = {
  reply: 'Based on SEC filings, Nvidia faces export-control risks...',
  tool_calls: [
    {
      name: 'search_sec_filings',
      arguments: { ticker: 'NVDA', form_type: '10-K' },
      result: {
        rows: [
          {
            chunk_id: 'chunk-1',
            accession_number: '0001234567-24-000001',
            form_type: '10-K',
            accepted_ts: '2024-02-21',
            source_url: 'https://sec.gov/filing/1',
            ticker: 'NVDA',
            section: 'risk_factors',
            retrieval_mode: 'hybrid',
          },
        ],
      },
      ok: true,
    },
  ],
  sources: [{ tool: 'search_sec_filings', chunk_id: 'chunk-1' }],
  available: true,
  empty: false,
};

const mockSavedNoteResponse = {
  reply: 'Note saved successfully.',
  tool_calls: [
    {
      name: 'save_research_note',
      arguments: { symbol: 'NVDA', content: 'Export controls risk' },
      result: { note_id: 'note-42', symbol: 'NVDA', status: 'saved' },
      ok: true,
    },
  ],
  sources: [],
  available: true,
  empty: false,
};

const mockFailedToolResponse = {
  reply: 'I was unable to complete the search.',
  tool_calls: [
    {
      name: 'search_sec_filings',
      arguments: { ticker: 'XYZ' },
      result: { error: 'retrieval_unavailable', message: 'Service down' },
      ok: false,
    },
  ],
  sources: [],
  available: true,
  empty: false,
};

function mockFetch(response: unknown = mockChatResponse) {
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url === '/api/agent/chat' && init?.method === 'POST') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(response) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

describe('ResearchAgent', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders suggested questions when conversation is empty', () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<ResearchAgent />);

    expect(screen.getByText(/Summarize Nvidia/)).toBeInTheDocument();
    expect(screen.getByText(/Find SEC evidence/)).toBeInTheDocument();
    expect(screen.getByText(/What risks does AMD/)).toBeInTheDocument();
    expect(screen.getByText(/Show recent market features/)).toBeInTheDocument();
    expect(screen.getByText(/Save a research note/)).toBeInTheDocument();
  });

  it('submits a suggested question and renders the grounded answer', async () => {
    vi.stubGlobal('fetch', mockFetch());
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize Nvidia/));

    await waitFor(() => {
      expect(screen.getByText(/Based on SEC filings/)).toBeInTheDocument();
    });

    expect(fetch).toHaveBeenCalledWith(
      '/api/agent/chat',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('renders a typed SEC evidence card from nested result rows', async () => {
    vi.stubGlobal('fetch', mockFetch());
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize Nvidia/));

    await waitFor(() => {
      expect(screen.getByTestId('source-card')).toBeInTheDocument();
    });

    expect(screen.getAllByText('NVDA').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('10-K')).toBeInTheDocument();
    expect(screen.getByText('2024-02-21')).toBeInTheDocument();
    expect(screen.getByText('risk_factors')).toBeInTheDocument();
    expect(screen.getByText('hybrid')).toBeInTheDocument();
    expect(screen.getByText('View source')).toBeInTheDocument();
  });

  it('renders failed tools as failed and saved notes with note id and Lakebase', async () => {
    vi.stubGlobal('fetch', mockFetch(mockSavedNoteResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Save a research note/));

    await waitFor(() => {
      expect(screen.getByText(/Note saved/)).toBeInTheDocument();
    });

    const noteElements = screen.getAllByText(/note-42/);
    expect(noteElements.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Lakebase')).toBeInTheDocument();
  });

  it('renders failed tool status', async () => {
    vi.stubGlobal('fetch', mockFetch(mockFailedToolResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize Nvidia/));

    await waitFor(() => {
      const failedElements = screen.getAllByText('Failed');
      expect(failedElements.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('keeps developer details collapsed by default', async () => {
    vi.stubGlobal('fetch', mockFetch());
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize Nvidia/));

    await waitFor(() => {
      expect(screen.getByTestId('developer-details')).toBeInTheDocument();
    });

    const details = screen.getByTestId('developer-details');
    expect(details).not.toHaveAttribute('open');
  });

  it('disables send while submitting and blocks empty input', async () => {
    let resolveChat: (v: unknown) => void;
    const chatPromise = new Promise((resolve) => {
      resolveChat = resolve;
    });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (url === '/api/agent/chat' && init?.method === 'POST') {
          return chatPromise.then((body) => ({ ok: true, json: () => Promise.resolve(body) }));
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }),
    );

    const user = userEvent.setup();
    render(<ResearchAgent />);

    const input = screen.getByPlaceholderText('Ask the research agent…');
    const sendButton = screen.getByRole('button', { name: 'Send' });

    // Empty input: button should be disabled
    expect(sendButton).toBeDisabled();

    // Type something
    await user.type(input, 'test question');
    expect(sendButton).not.toBeDisabled();

    // Submit
    await user.click(sendButton);

    // While sending, button should be disabled
    expect(sendButton).toBeDisabled();

    // Resolve the request
    await act(async () => {
      resolveChat!(mockChatResponse);
    });

    // After send completes, input is cleared so button stays disabled (empty input)
    await waitFor(() => {
      expect(sendButton).toBeDisabled();
    });

    // Typing new text re-enables the button
    await user.type(input, 'another question');
    expect(sendButton).not.toBeDisabled();
  });

  it('keeps the question after an API failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (url === '/api/agent/chat' && init?.method === 'POST') {
          return Promise.resolve({ ok: false, status: 500, statusText: 'Internal Server Error', json: () => Promise.resolve({ detail: 'Server error' }) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }),
    );

    const user = userEvent.setup();
    render(<ResearchAgent />);

    const input = screen.getByPlaceholderText('Ask the research agent…');
    await user.type(input, 'my important question');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(screen.getByDisplayValue('my important question')).toBeInTheDocument();
    });
  });

  it('does not render unsupported or simulated execution stages', async () => {
    vi.stubGlobal('fetch', mockFetch());
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize Nvidia/));

    await waitFor(() => {
      expect(screen.getByTestId('execution-trace')).toBeInTheDocument();
    });

    // Should only have the three defined stages
    expect(screen.getByTestId('trace-retrieval')).toBeInTheDocument();
    expect(screen.getByTestId('trace-tool_execution')).toBeInTheDocument();
    expect(screen.getByTestId('trace-response')).toBeInTheDocument();

    // No simulated timing stages
    expect(screen.queryByText(/model inference/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/embedding/i)).not.toBeInTheDocument();
  });

  it('blocks whitespace-only input', async () => {
    vi.stubGlobal('fetch', mockFetch());
    const user = userEvent.setup();
    render(<ResearchAgent />);

    const input = screen.getByPlaceholderText('Ask the research agent…');
    const sendButton = screen.getByRole('button', { name: 'Send' });

    await user.type(input, '   ');
    expect(sendButton).toBeDisabled();
  });

  it('renders the evidence panel empty state when no messages', () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<ResearchAgent />);

    expect(screen.getByTestId('evidence-panel-empty')).toBeInTheDocument();
    expect(screen.getByText(/No evidence yet/)).toBeInTheDocument();
  });

  it('renders error states for unavailable retrieval results', async () => {
    const unavailableResponse = {
      reply: 'No results found.',
      tool_calls: [
        {
          name: 'search_sec_filings',
          arguments: { ticker: 'XYZ' },
          result: { rows: [{ error: 'no_coverage', message: 'Ticker not covered', ticker: 'XYZ' }] },
          ok: true,
        },
      ],
      sources: [],
      available: true,
      empty: false,
    };
    vi.stubGlobal('fetch', mockFetch(unavailableResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.type(screen.getByPlaceholderText('Ask the research agent…'), 'test');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(screen.getByText('No results found.')).toBeInTheDocument();
    });
  });

  it('renders error rows honestly and not as source cards', async () => {
    const mixedResponse = {
      reply: 'Partial results.',
      tool_calls: [
        {
          name: 'search_sec_filings',
          arguments: { ticker: 'NVDA' },
          result: {
            rows: [
              { error: 'no_coverage', ticker: 'XYZ', message: 'Ticker not covered' },
              {
                chunk_id: 'chunk-1',
                accession_number: '0001234567-24-000001',
                form_type: '10-K',
                accepted_ts: '2024-02-21',
                source_url: 'https://sec.gov/filing/1',
                ticker: 'NVDA',
                section: 'risk_factors',
                retrieval_mode: 'hybrid',
              },
            ],
          },
          ok: true,
        },
      ],
      sources: [],
      available: true,
      empty: false,
    };
    vi.stubGlobal('fetch', mockFetch(mixedResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.type(screen.getByPlaceholderText('Ask the research agent…'), 'test');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(screen.getByText(/No SEC filings processed for XYZ yet/)).toBeInTheDocument();
    });

    // Error rows should NOT be rendered as source cards
    const sourceCards = screen.getAllByTestId('source-card');
    expect(sourceCards).toHaveLength(1);
    expect(sourceCards[0]).toHaveTextContent('NVDA');
  });

  it('shows Failed badge on tool card when ok is false', async () => {
    vi.stubGlobal('fetch', mockFetch(mockFailedToolResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize Nvidia/));

    await waitFor(() => {
      const toolCard = screen.getByTestId('tool-call-0');
      expect(toolCard).toHaveTextContent('Failed');
    });

    // The badge should be on the tool card, not just in execution trace
    const toolCard = screen.getByTestId('tool-call-0');
    const badge = toolCard.querySelector('.bg-red-100, .dark\\:bg-red-900\\/30');
    expect(badge).not.toBeNull();
  });

  it('does not show note saved confirmation when note_id is absent', async () => {
    const noNoteIdResponse = {
      reply: 'Note processed.',
      tool_calls: [
        {
          name: 'save_research_note',
          arguments: { symbol: 'NVDA', content: 'test' },
          result: { symbol: 'NVDA', status: 'saved' },
          ok: true,
        },
      ],
      sources: [],
      available: true,
      empty: false,
    };
    vi.stubGlobal('fetch', mockFetch(noNoteIdResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Save a research note/));

    await waitFor(() => {
      expect(screen.getByText('Note processed.')).toBeInTheDocument();
    });

    // Should NOT show "Research note saved to Lakebase" without note_id
    expect(screen.queryByText(/Research note saved to Lakebase/)).not.toBeInTheDocument();
  });

  it('shows agent-unavailable state when available is false and no tool calls', async () => {
    const unavailableResponse = {
      reply: 'Agent is unavailable.',
      tool_calls: [],
      sources: [],
      available: false,
      empty: true,
    };
    vi.stubGlobal('fetch', mockFetch(unavailableResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.type(screen.getByPlaceholderText('Ask the research agent…'), 'test');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/Agent tools are unavailable/);
    });
  });

  it('renders follow-up questions when API returns them', async () => {
    const followUpResponse = {
      ...mockChatResponse,
      follow_ups: ['How did NVDA grow?', 'What are the risks?'],
    };
    vi.stubGlobal('fetch', mockFetch(followUpResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize Nvidia/));

    await waitFor(() => {
      expect(screen.getByText('How did NVDA grow?')).toBeInTheDocument();
      expect(screen.getByText('What are the risks?')).toBeInTheDocument();
    });

    // Clicking a follow-up should submit it
    await user.click(screen.getByText('How did NVDA grow?'));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(2);
    });
  });
});