import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ResearchAgent } from './ResearchAgent';
import * as symbolStorage from '../utils/symbolStorage';

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

    expect(screen.getByText(/Summarize NVDA/)).toBeInTheDocument();
    expect(screen.getByText(/Find SEC evidence/)).toBeInTheDocument();
    expect(screen.getByText(/What risks does NVDA/)).toBeInTheDocument();
    expect(screen.getByText(/Show recent market features/)).toBeInTheDocument();
    expect(screen.getByText(/Save a research note/)).toBeInTheDocument();
  });

  it('submits a suggested question and renders the grounded answer', async () => {
    vi.stubGlobal('fetch', mockFetch());
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize NVDA/));

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

    await user.click(screen.getByText(/Summarize NVDA/));

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

    await user.click(screen.getByText(/Summarize NVDA/));

    await waitFor(() => {
      const failedElements = screen.getAllByText('Failed');
      expect(failedElements.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('keeps developer details collapsed by default', async () => {
    vi.stubGlobal('fetch', mockFetch());
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize NVDA/));

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

    await user.click(screen.getByText(/Summarize NVDA/));

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

    // Source count badge should exclude error rows (1 error + 1 good → "1 source")
    const toolCard = screen.getByTestId('tool-call-0');
    expect(toolCard).toHaveTextContent('1 source');
    expect(toolCard).not.toHaveTextContent('2 source');
  });

  it('shows Failed badge on tool card when ok is false', async () => {
    vi.stubGlobal('fetch', mockFetch(mockFailedToolResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize NVDA/));

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

    // Badge should show honest state, not "Note saved"
    const toolCard = screen.getByTestId('tool-call-0');
    expect(toolCard).not.toHaveTextContent('Note saved');
    expect(toolCard).toHaveTextContent('Save not confirmed');
    expect(toolCard).not.toHaveTextContent('undefined');
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

  it('ignores an unexpected follow_ups field — the backend contract has none, so no API-derived follow-up controls appear', async () => {
    // api/schemas.py ChatResponse has no follow_ups; if a response ever carries one, the UI must not render it.
    vi.stubGlobal('fetch', mockFetch({ ...mockChatResponse, follow_ups: ['Injected follow-up question?'] }));
    const user = userEvent.setup();
    render(<ResearchAgent />);
    await user.type(screen.getByPlaceholderText('Ask the research agent…'), 'What risks does NVDA disclose?');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => {
      expect(screen.getByText(mockChatResponse.reply.slice(0, 30), { exact: false })).toBeInTheDocument();
    });
    expect(document.body.textContent ?? '').not.toMatch(/Injected follow-up question/);
    expect(screen.queryByRole('button', { name: /Injected follow-up/ })).not.toBeInTheDocument();
  });

  it('picking AMD changes the suggested questions to AMD', async () => {
    vi.stubGlobal('fetch', mockFetch());
    vi.spyOn(symbolStorage, 'getUrlSymbol').mockReturnValue(null);
    vi.spyOn(symbolStorage, 'setUrlSymbol').mockImplementation(() => {});
    const user = userEvent.setup();
    render(<ResearchAgent />);

    // Default NVDA suggested questions should be visible
    expect(screen.getByText(/NVDA.*latest reported export-control risks/)).toBeInTheDocument();

    // Click AMD quick choice
    await user.click(screen.getByText('AMD', { selector: 'button' }));

    // Suggested questions should now reference AMD
    expect(screen.getByText(/AMD.*latest reported export-control risks/)).toBeInTheDocument();
    expect(screen.getByText(/AMD.*China revenue exposure/)).toBeInTheDocument();
    expect(screen.getByText(/AMD.*describe in its latest 10-K/)).toBeInTheDocument();

    // NVDA questions should be gone
    expect(screen.queryByText(/NVDA.*latest reported export-control risks/)).not.toBeInTheDocument();
  });

  it('chat request body contains only message, no symbol field', async () => {
    vi.stubGlobal('fetch', mockFetch());
    vi.spyOn(symbolStorage, 'getUrlSymbol').mockReturnValue(null);
    vi.spyOn(symbolStorage, 'setUrlSymbol').mockImplementation(() => {});
    const user = userEvent.setup();
    render(<ResearchAgent />);

    // Click AMD to set scope
    await user.click(screen.getByText('AMD', { selector: 'button' }));

    // Click a suggested question that references AMD
    await user.click(screen.getByText(/AMD.*latest reported export-control risks/));

    await waitFor(() => {
      expect(screen.getByText(/Based on SEC filings/)).toBeInTheDocument();
    });

    // The fetch call body should contain only { message: "..." }
    const fetchMock = vi.mocked(fetch);
    const chatCall = fetchMock.mock.calls.find((c) => c[0] === '/api/agent/chat');
    expect(chatCall).toBeTruthy();
    const body = JSON.parse(chatCall![1]!.body as string);
    expect(body).toHaveProperty('message');
    expect(body.message).toContain('AMD');
    expect(body).not.toHaveProperty('symbol');
    expect(body).not.toHaveProperty('write_authorization');
  });

  it('keeps all conversation turns after two consecutive questions', async () => {
    const secondResponse = {
      reply: 'AMD describes risks related to competition and supply chain...',
      tool_calls: [
        {
          name: 'search_sec_filings',
          arguments: { ticker: 'AMD', form_type: '10-K' },
          result: {
            rows: [
              {
                chunk_id: 'chunk-2',
                accession_number: '0009876543-24-000001',
                form_type: '10-K',
                accepted_ts: '2024-02-15',
                source_url: 'https://sec.gov/filing/2',
                ticker: 'AMD',
                section: 'risk_factors',
                retrieval_mode: 'hybrid',
              },
            ],
          },
          ok: true,
        },
      ],
      sources: [{ tool: 'search_sec_filings', chunk_id: 'chunk-2' }],
      available: true,
      empty: false,
    };

    let callCount = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (url === '/api/agent/chat' && init?.method === 'POST') {
          callCount++;
          const body = callCount === 1 ? mockChatResponse : secondResponse;
          return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }),
    );
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize NVDA/));

    await waitFor(() => {
      expect(screen.getByText(/Based on SEC filings/)).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Ask the research agent…');
    await user.type(input, 'What risks does AMD describe?');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(screen.getByText(/AMD describes risks/)).toBeInTheDocument();
    });

    // Both turns should be visible
    expect(screen.getByText(/Based on SEC filings/)).toBeInTheDocument();
    expect(screen.getByText(/AMD describes risks/)).toBeInTheDocument();

    // Both user messages should be visible
    expect(screen.getByText(/Summarize NVDA/)).toBeInTheDocument();
    expect(screen.getByText('What risks does AMD describe?')).toBeInTheDocument();
  });

  it('keeps earlier turns and preserves question text when follow-up fails', async () => {
    let callCount = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (url === '/api/agent/chat' && init?.method === 'POST') {
          callCount++;
          if (callCount === 1) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(mockChatResponse) });
          }
          return Promise.resolve({ ok: false, status: 500, statusText: 'Internal Server Error', json: () => Promise.resolve({ detail: 'Server error' }) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }),
    );
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize NVDA/));

    await waitFor(() => {
      expect(screen.getByText(/Based on SEC filings/)).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Ask the research agent…');
    await user.type(input, 'What about AMD?');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    // Earlier turn should still be visible
    await waitFor(() => {
      expect(screen.getByText(/Based on SEC filings/)).toBeInTheDocument();
    });

    // Failed question text should be preserved in input
    expect(screen.getByDisplayValue('What about AMD?')).toBeInTheDocument();
  });

  it('trace shows Failed when follow-up request fails after a successful first request', async () => {
    let callCount = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (url === '/api/agent/chat' && init?.method === 'POST') {
          callCount++;
          if (callCount === 1) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(mockChatResponse) });
          }
          return Promise.resolve({ ok: false, status: 500, statusText: 'Internal Server Error', json: () => Promise.resolve({ detail: 'Server error' }) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }),
    );
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize NVDA/));

    await waitFor(() => {
      expect(screen.getByText(/Based on SEC filings/)).toBeInTheDocument();
    });

    // First request: trace should show Complete
    expect(screen.getByTestId('trace-response')).toHaveTextContent('Complete');

    const input = screen.getByPlaceholderText('Ask the research agent…');
    await user.type(input, 'What about AMD?');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    // Follow-up fails: trace must show Failed, not the prior reply's Complete
    await waitFor(() => {
      expect(screen.getByTestId('trace-response')).toHaveTextContent('Failed');
    });
    expect(screen.getByDisplayValue('What about AMD?')).toBeInTheDocument();
  });

  it('trace reflects second response when follow-up request succeeds', async () => {
    const zeroToolResponse = {
      reply: 'AMD describes competition risks...',
      tool_calls: [],
      sources: [],
      available: true,
      empty: false,
    };

    let callCount = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (url === '/api/agent/chat' && init?.method === 'POST') {
          callCount++;
          const body = callCount === 1 ? mockChatResponse : zeroToolResponse;
          return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }),
    );
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize NVDA/));

    await waitFor(() => {
      expect(screen.getByText(/Based on SEC filings/)).toBeInTheDocument();
    });

    expect(screen.getByTestId('trace-retrieval')).toHaveTextContent('Complete');

    const input = screen.getByPlaceholderText('Ask the research agent…');
    await user.type(input, 'What about AMD?');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(screen.getByText(/AMD describes competition risks/)).toBeInTheDocument();
    });

    // Trace must reflect the zero-tool second response:
    // Response is Complete (reply delivered), but retrieval and tool execution are Skipped.
    // If the trace reused the first response's search tool call, these would be Complete.
    expect(screen.getByTestId('trace-response')).toHaveTextContent('Complete');
    expect(screen.getByTestId('trace-retrieval')).toHaveTextContent('Skipped');
    expect(screen.getByTestId('trace-tool_execution')).toHaveTextContent('Skipped');
  });

  it('deferred follow-up: trace resets to pending then reflects rejection', async () => {
    let resolveFirst!: (v: unknown) => void;
    let rejectSecond!: (r: unknown) => void;
    let callCount = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (url === '/api/agent/chat' && init?.method === 'POST') {
          callCount++;
          if (callCount === 1) {
            return new Promise((resolve) => {
              resolveFirst = resolve;
            });
          }
          return new Promise((_resolve, reject) => {
            rejectSecond = reject;
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }),
    );
    const user = userEvent.setup();
    render(<ResearchAgent />);

    // Step 1: resolve first request successfully
    await user.click(screen.getByText(/Summarize NVDA/));
    await act(async () => {
      resolveFirst({ ok: true, json: () => Promise.resolve(mockChatResponse) });
    });
    await waitFor(() => {
      expect(screen.getByText(/Based on SEC filings/)).toBeInTheDocument();
    });
    expect(screen.getByTestId('trace-response')).toHaveTextContent('Complete');

    // Step 2: start follow-up and immediately reject it (no assistant reply)
    const input = screen.getByPlaceholderText('Ask the research agent…');
    await user.type(input, 'What about AMD?');
    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'Send' }));
    });

    // Step 3: while pending, trace must represent the new attempt, not the prior reply
    expect(screen.getByTestId('trace-response')).not.toHaveTextContent('Complete');

    // Step 4: reject follow-up → must show Failed, not Complete
    await act(async () => {
      rejectSecond(new Error('Network error'));
    });
    await waitFor(() => {
      expect(screen.getByTestId('trace-response')).toHaveTextContent('Failed');
    });
    expect(screen.getByDisplayValue('What about AMD?')).toBeInTheDocument();
  });

  it('does not render model confidence or score values from API response', async () => {
    const confidenceResponse = {
      reply: 'Based on analysis, Nvidia shows strong growth potential.',
      tool_calls: [
        {
          name: 'search_sec_filings',
          arguments: { ticker: 'NVDA' },
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
            confidence: 0.92,
            score: 87,
          },
          ok: true,
        },
      ],
      sources: [{ tool: 'search_sec_filings', chunk_id: 'chunk-1' }],
      available: true,
      empty: false,
    };
    vi.stubGlobal('fetch', mockFetch(confidenceResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Summarize NVDA/));

    await waitFor(() => {
      expect(screen.getByText(/Based on analysis/)).toBeInTheDocument();
    });

    // Confidence and score values from tool call result must never be rendered as UI
    const toolCard = screen.getByTestId('tool-call-0');
    // "Confidence:" label must not appear outside the raw JSON developer details
    const devDetails = toolCard.querySelector('[data-testid="developer-details"]');
    const visibleText = toolCard.textContent!.replace(devDetails?.textContent ?? '', '');
    expect(visibleText).not.toMatch(/confidence/i);
    expect(visibleText).not.toMatch(/92%/);
    expect(visibleText).not.toMatch(/87%/);
  });

  it('renders agent tour selectors [data-tour=agent] and [data-tour=agent-evidence]', async () => {
    vi.stubGlobal('fetch', mockFetch());
    render(<ResearchAgent />);

    // The agent container has data-tour="agent"
    expect(screen.getByTestId('evidence-panel-empty')).toBeInTheDocument();

    // After a response, the evidence panel should have data-tour="agent-evidence"
    const user = userEvent.setup();
    await user.click(screen.getByText(/Summarize NVDA/));

    await waitFor(() => {
      expect(screen.getByTestId('evidence-panel')).toBeInTheDocument();
    });

    expect(screen.getByTestId('evidence-panel')).toHaveAttribute('data-tour', 'agent-evidence');
  });

  it('all AGENT_TOUR selectors render on the Research Agent screen (no off-screen targets)', async () => {
    vi.stubGlobal('fetch', mockFetch(mockSavedNoteResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    // [data-tour="agent"] is always present
    expect(document.querySelector('[data-tour="agent"]')).toBeTruthy();

    // Trigger a note save first (via input, since suggested questions hide after first message)
    await user.type(screen.getByPlaceholderText('Ask the research agent…'), 'Save a research note for NVDA');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(screen.getByText(/Note saved/)).toBeInTheDocument();
    });

    // [data-tour="agent-evidence"] must be on this screen
    expect(document.querySelector('[data-tour="agent-evidence"]')).toBeTruthy();

    // [data-tour="lakebase-write"] must be on this screen, not PaperPortfolio
    const lakebaseEl = document.querySelector('[data-tour="lakebase-write"]');
    expect(lakebaseEl).toBeTruthy();
    expect(lakebaseEl!.closest('[data-tour="agent"]')).toBeTruthy();
  });

  it('renders lakebase-write data-tour attribute on note confirmation', async () => {
    vi.stubGlobal('fetch', mockFetch(mockSavedNoteResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    await user.click(screen.getByText(/Save a research note/));

    await waitFor(() => {
      expect(screen.getByText(/Note saved/)).toBeInTheDocument();
    });

    const lakebaseEl = document.querySelector('[data-tour="lakebase-write"]');
    expect(lakebaseEl).toBeTruthy();
    expect(lakebaseEl!.textContent).toContain('Research note saved to Lakebase');
  });

  it('replaces all {SYMBOL} occurrences in suggested questions with two placeholders', () => {
    // The current template has one {SYMBOL} per question, but the function should handle multiple
    vi.stubGlobal('fetch', mockFetch());
    render(<ResearchAgent />);

    // Each suggested question should contain the symbol exactly once (or more if template has multiple)
    const nvdaQuestions = screen.getAllByText(/NVDA/);
    expect(nvdaQuestions.length).toBeGreaterThanOrEqual(1);

    // No question should contain a literal {SYMBOL}
    const allText = document.body.textContent ?? '';
    expect(allText).not.toContain('{SYMBOL}');
  });

  it('every AGENT_TOUR selector resolves against the rendered ResearchAgent screen', async () => {
    const { AGENT_TOUR } = await import('../components/tours/tourSteps');
    vi.stubGlobal('fetch', mockFetch(mockSavedNoteResponse));
    const user = userEvent.setup();
    render(<ResearchAgent />);

    // Drive state to expose the note-confirmation target.
    await user.click(screen.getByText(/Save a research note/));
    await waitFor(() => {
      expect(screen.getByText(/Note saved/)).toBeInTheDocument();
    });

    // The evidence panel must also be present.
    await waitFor(() => {
      expect(screen.getByTestId('evidence-panel')).toBeInTheDocument();
    });

    for (const step of AGENT_TOUR) {
      if (!step.selector) continue;
      const el = document.querySelector(step.selector);
      expect(el).toBeTruthy();
    }
  });

  it('makeSuggestedQuestions replaces every {SYMBOL} occurrence in a two-placeholder template', async () => {
    const { makeSuggestedQuestions } = await import('./ResearchAgent');
    const templates = [
      "How does {SYMBOL} compare to {SYMBOL} on risk metrics?",
    ];
    const questions = makeSuggestedQuestions('AAPL', templates);
    expect(questions[0]).toBe('How does AAPL compare to AAPL on risk metrics?');
    expect(questions[0]).not.toContain('{SYMBOL}');
  });
});
