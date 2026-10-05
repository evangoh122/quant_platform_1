import { useState } from 'react';
import { api } from '../api/client';
import type { ChatResponse } from '../api/types';
import { Card } from '../components/Card';
import { LoadingState } from '../components/LoadingState';

interface Message {
  role: 'user' | 'assistant';
  text: string;
  toolCalls: ChatResponse['tool_calls'];
}

export function ResearchAgent() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(text?: string) {
    const message = (text ?? input).trim();
    if (!message) return;
    setInput('');
    setSending(true);
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', text: message, toolCalls: [] }]);
    try {
      const resp = await api.chat(message);
      setMessages((prev) => [...prev, { role: 'assistant', text: resp.reply, toolCalls: resp.tool_calls }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  return (
    <div data-tour="agent" className="space-y-4">
      <h1 className="text-xl font-semibold">AI Research Agent</h1>

      <Card title="Conversation" subtitle="Every tool call is surfaced as auditable evidence">
        <div className="max-h-96 space-y-3 overflow-y-auto">
          {messages.length === 0 && (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Ask about signals, market features, or SEC filings — e.g. “latest signal for NVDA”.
            </p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`rounded-lg p-3 ${m.role === 'user' ? 'bg-slate-100 dark:bg-slate-800' : 'bg-blue-50 dark:bg-blue-950/40'}`}>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{m.role}</div>
              <p className="mt-1 text-sm text-slate-800 dark:text-slate-200">{m.text}</p>
              {m.toolCalls.length > 0 && (
                <div className="mt-2 space-y-1">
                  {m.toolCalls.map((tc, j) => (
                    <div key={j} className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900">
                      <span className="font-mono font-semibold">{tc.name}</span>
                      <span className={tc.ok ? 'text-emerald-600' : 'text-red-600'}> {tc.ok ? 'ok' : 'failed'}</span>
                      <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all text-[11px] text-slate-500">
                        {JSON.stringify(tc.result ?? tc.arguments, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          {sending && <LoadingState label="Agent is working…" />}
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>

        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            placeholder="Ask the research agent…"
          />
          <button
            type="submit"
            disabled={sending}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
          >
            Send
          </button>
        </form>
      </Card>
    </div>
  );
}
