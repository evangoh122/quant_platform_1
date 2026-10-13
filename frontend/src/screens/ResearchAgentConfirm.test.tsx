import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ResearchAgent } from './ResearchAgent';

const pendingResponse = {
  reply:
    'I prepared a write action but have not executed it: save_research_note for NVDA. Confirm the write to execute exactly this action, or cancel to discard it.',
  tool_calls: [
    {
      name: 'get_latest_signal',
      arguments: { symbol: 'NVDA' },
      result: { direction: 'LONG' },
      ok: true,
    },
  ],
  sources: [],
  available: true,
  empty: false,
  pending_action: {
    tool: 'save_research_note',
    args: {
      symbol: 'NVDA',
      note: 'Export controls remain a key risk',
      evidence_ids: ['chunk-001', 'chunk-002'],
    },
    token: 'signed-proposal-token',
    expires_at: '2026-10-13T11:00:00+00:00',
    summary: 'save_research_note for NVDA: Export controls remain a key risk',
  },
  write_result: null,
};

const confirmResponse = {
  reply: 'Confirmed. The proposed write has been executed.',
  tool_calls: [],
  sources: [],
  available: true,
  empty: false,
  pending_action: null,
  write_result: {
    note_id: 'note-77',
    symbol: 'NVDA',
    status: 'saved',
    replay: false,
    trace_id: 'trace-xyz',
  },
};

const emptyNotes = {
  data: [],
  count: 0,
  empty: true,
  source: 'research_notes',
  freshness: { state: 'empty', table: 'research_notes', detail: '0 rows' },
};

const savedNotesEnvelope = {
  data: [
    {
      note_id: 'note-77',
      symbol: 'NVDA',
      note_text: 'Export controls remain a key risk',
      created_at: '2026-10-13T10:00:00+00:00',
    },
  ],
  count: 1,
  empty: false,
  source: 'research_notes',
  freshness: { state: 'fresh', table: 'research_notes', detail: '1 rows' },
};

interface MockOptions {
  confirmResponse?: unknown;
  confirmError?: string;
  notesResponses?: unknown[];
}

function mockFetch(options: MockOptions = {}) {
  let notesCalls = 0;
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url === '/api/agent/chat' && init?.method === 'POST') {
      const body = JSON.parse(init.body as string) as { confirm_token?: string };
      if (body.confirm_token) {
        if (options.confirmError) {
          return Promise.resolve({
            ok: false,
            status: 500,
            statusText: 'Internal Server Error',
            json: () => Promise.resolve({ detail: options.confirmError }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(options.confirmResponse ?? confirmResponse),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(pendingResponse) });
    }
    if (url === '/api/notes') {
      const list = options.notesResponses ?? [emptyNotes, savedNotesEnvelope];
      const payload = list[Math.min(notesCalls, list.length - 1)];
      notesCalls += 1;
      return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

async function sendQuestion() {
  const user = userEvent.setup();
  render(<ResearchAgent />);
  await user.type(
    screen.getByPlaceholderText('Ask the research agent…'),
    'Save a research note for NVDA',
  );
  await user.click(screen.getByRole('button', { name: 'Send' }));
  await waitFor(() => {
    expect(screen.getByTestId('pending-confirm-card')).toBeInTheDocument();
  });
  return user;
}

function confirmPosts(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.filter((c) => {
    if (c[0] !== '/api/agent/chat' || c[1]?.method !== 'POST') return false;
    const body = JSON.parse(c[1].body as string) as { confirm_token?: string };
    return Boolean(body.confirm_token);
  });
}

describe('ResearchAgent confirm-and-write', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders a confirmation card with tool, symbol, note text and evidence ids', async () => {
    vi.stubGlobal('fetch', mockFetch());
    await sendQuestion();

    const card = screen.getByTestId('pending-confirm-card');
    expect(card).toHaveTextContent('save_research_note');
    expect(card).toHaveTextContent('NVDA');
    expect(screen.getByTestId('pending-note-text')).toHaveTextContent(
      'Export controls remain a key risk',
    );
    expect(screen.getByTestId('pending-evidence-ids')).toHaveTextContent('chunk-001');
    expect(screen.getByRole('button', { name: 'Confirm write' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel write' })).toBeInTheDocument();
  });

  it('sends exactly one confirm request even on double click', async () => {
    const fetchMock = mockFetch();
    vi.stubGlobal('fetch', fetchMock);
    const user = await sendQuestion();

    await user.dblClick(screen.getByRole('button', { name: 'Confirm write' }));

    await waitFor(() => {
      expect(screen.getByTestId('confirm-saved')).toBeInTheDocument();
    });

    const posts = confirmPosts(fetchMock);
    expect(posts).toHaveLength(1);
    const body = JSON.parse(posts[0][1].body as string);
    expect(body).toEqual({ confirm_token: 'signed-proposal-token' });
    expect(body).not.toHaveProperty('args');
    expect(body).not.toHaveProperty('idempotency_key');
  });

  it('success renders the server note id and trace id and refreshes saved notes', async () => {
    vi.stubGlobal('fetch', mockFetch());
    const user = await sendQuestion();

    await user.click(screen.getByRole('button', { name: 'Confirm write' }));

    await waitFor(() => {
      expect(screen.getByTestId('confirm-saved')).toHaveTextContent('note-77');
    });
    expect(screen.getByTestId('confirm-saved')).toHaveTextContent('trace-xyz');

    await waitFor(() => {
      expect(screen.getByTestId('saved-notes')).toHaveTextContent(
        'Export controls remain a key risk',
      );
    });
    expect(screen.getByTestId('saved-notes')).toHaveTextContent('note-77');
  });

  it('renders success strictly from the server write_result', async () => {
    const noResult = {
      ...confirmResponse,
      write_result: null,
    };
    vi.stubGlobal('fetch', mockFetch({ confirmResponse: noResult }));
    const user = await sendQuestion();

    await user.click(screen.getByRole('button', { name: 'Confirm write' }));

    // No hardcoded success: without a server write_result there is no "Saved" state.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Confirm write' })).toBeInTheDocument();
    });
    expect(screen.queryByTestId('confirm-saved')).not.toBeInTheDocument();
  });

  it('Cancel discards the token client-side and sends nothing', async () => {
    const fetchMock = mockFetch();
    vi.stubGlobal('fetch', fetchMock);
    const user = await sendQuestion();

    await user.click(screen.getByRole('button', { name: 'Cancel write' }));

    await waitFor(() => {
      expect(screen.queryByTestId('pending-confirm-card')).not.toBeInTheDocument();
    });
    expect(confirmPosts(fetchMock)).toHaveLength(0);
  });

  it('renders the safe error message when the confirm fails', async () => {
    vi.stubGlobal('fetch', mockFetch({ confirmError: 'confirmation token has expired' }));
    const user = await sendQuestion();

    await user.click(screen.getByRole('button', { name: 'Confirm write' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('confirmation token has expired');
    });
    expect(screen.queryByTestId('confirm-saved')).not.toBeInTheDocument();
  });

  it('renders Added <symbol> to watchlist for a watchlist confirm', async () => {
    const watchlistPending = {
      ...pendingResponse,
      pending_action: {
        tool: 'add_to_watchlist',
        args: { symbol: 'AMD' },
        token: 'watchlist-token',
        expires_at: '2026-10-13T11:00:00+00:00',
        summary: 'add_to_watchlist for AMD',
      },
    };
    const watchlistConfirm = {
      ...confirmResponse,
      write_result: {
        note_id: null,
        symbol: 'AMD',
        status: 'added',
        replay: false,
        trace_id: 'trace-wl',
      },
    };
    let notesCalls = 0;
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/agent/chat' && init?.method === 'POST') {
        const body = JSON.parse(init.body as string) as { confirm_token?: string };
        if (body.confirm_token) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(watchlistConfirm) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve(watchlistPending) });
      }
      if (url === '/api/notes') {
        notesCalls += 1;
        return Promise.resolve({ ok: true, json: () => Promise.resolve(emptyNotes) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<ResearchAgent />);
    await user.type(
      screen.getByPlaceholderText('Ask the research agent…'),
      'Add AMD to watchlist',
    );
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => {
      expect(screen.getByTestId('pending-confirm-card')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Confirm write' }));

    await waitFor(() => {
      expect(screen.getByTestId('confirm-saved')).toHaveTextContent('Added AMD to watchlist');
    });
    expect(screen.getByTestId('confirm-saved')).toHaveTextContent('trace-wl');
  });
});
