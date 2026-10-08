import { useState, useRef, useEffect, useMemo } from 'react';
import { api } from '../api/client';
import type { ChatResponse } from '../api/types';
import { Card } from '../components/Card';
import { LoadingState } from '../components/LoadingState';
import { ExecutionTrace } from '../components/ExecutionTrace';
import { EvidencePanel, hasValidNoteId } from '../components/evidence';
import { SymbolPicker } from '../components/SymbolPicker';
import symbols from '../data/symbols.json';

const BASE_SUGGESTED_QUESTIONS = [
  "Summarize {SYMBOL}'s latest reported export-control risks.",
  "Find SEC evidence about {SYMBOL}'s China revenue exposure.",
  "What risks does {SYMBOL} describe in its latest 10-K?",
  "Show recent market features for {SYMBOL}.",
  "Save a research note for {SYMBOL}: export controls remain a key risk.",
];

export function makeSuggestedQuestions(symbol: string, templates?: string[]): string[] {
  const base = templates ?? BASE_SUGGESTED_QUESTIONS;
  return base.map((q) => q.replace(/\{SYMBOL\}/g, symbol));
}

interface Message {
  role: 'user' | 'assistant';
  text: string;
  toolCalls: ChatResponse['tool_calls'];
  available: boolean;
}

interface AttemptTrace {
  toolCalls: ChatResponse['tool_calls'];
  reply?: string;
  available: boolean;
}

export function ResearchAgent() {
  const [symbol, setSymbol] = useState('NVDA');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentAttempt, setCurrentAttempt] = useState<AttemptTrace | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const secList = (symbols as { sec: string[] }).sec;
  const hasCoverage = secList.includes(symbol.toUpperCase());
  const suggestedQuestions = useMemo(() => makeSuggestedQuestions(symbol), [symbol]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, sending]);

  async function send(text?: string) {
    const message = (text ?? input).trim();
    if (!message) return;
    const questionToRestore = text ? input : message;
    setInput('');
    setSending(true);
    setError(null);
    setCurrentAttempt(null);
    setMessages((prev) => [...prev, { role: 'user', text: message, toolCalls: [], available: true }]);
    try {
      const resp = await api.chat(message);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: resp.reply, toolCalls: resp.tool_calls, available: resp.available },
      ]);
      setCurrentAttempt({ toolCalls: resp.tool_calls, reply: resp.reply, available: resp.available });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setInput(questionToRestore);
      setCurrentAttempt({ toolCalls: [], reply: undefined, available: false });
    } finally {
      setSending(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    void send();
  }

  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');

  const traceToolCalls = currentAttempt?.toolCalls ?? [];
  const traceReply = currentAttempt?.reply;
  const traceAvailable = currentAttempt?.available ?? true;

  return (
    <div data-tour="agent" className="space-y-4">
      <h1 className="text-xl font-semibold">AI Research Agent</h1>

      <SymbolPicker
        value={symbol}
        onChange={setSymbol}
        list="sec"
        hasCoverage={hasCoverage}
        label="Scope"
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        <Card title="Conversation" subtitle="Every tool call is surfaced as auditable evidence">
          <div ref={scrollRef} className="max-h-[32rem] space-y-3 overflow-y-auto">
            {messages.length === 0 && (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Ask about signals, market features, or SEC filings.
              </p>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`rounded-lg p-3 ${
                  m.role === 'user'
                    ? 'bg-slate-100 dark:bg-slate-800'
                    : 'bg-blue-50 dark:bg-blue-950/40'
                }`}
              >
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {m.role}
                </div>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-800 dark:text-slate-200">
                  {m.text}
                </p>
                {m.role === 'assistant' && m.toolCalls.some((tc) => tc.name === 'save_research_note' && tc.ok && hasValidNoteId(tc)) && (
                  <div data-tour="lakebase-write" className="mt-2 rounded-md border border-emerald-200 bg-emerald-50 p-2 text-xs text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300">
                    Research note saved to Lakebase.
                  </div>
                )}
              </div>
            ))}
            {sending && <LoadingState label="Agent is working…" />}
            {error && (
              <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-600 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
                {error}
              </div>
            )}
          </div>

          {messages.length === 0 && (
            <div className="mt-4 space-y-2">
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                Suggested questions
              </p>
              <div className="flex flex-wrap gap-2">
                {suggestedQuestions.map((q) => (
                  <button
                    key={q}
                    type="button"
                    disabled={sending}
                    onClick={() => void send(q)}
                    className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          <form className="mt-3 flex gap-2" onSubmit={handleSubmit}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
              placeholder="Ask the research agent…"
            />
            <button
              type="submit"
              disabled={sending || !input.trim()}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
            >
              Send
            </button>
          </form>
        </Card>

        <div className="space-y-4">
          <ExecutionTrace
            toolCalls={traceToolCalls}
            available={traceAvailable}
            sending={sending}
            reply={traceReply}
            attempted={messages.length > 0}
          />
          <EvidencePanel
            toolCalls={lastAssistant?.toolCalls ?? []}
            available={lastAssistant?.available ?? true}
            sending={sending}
          />
        </div>
      </div>
    </div>
  );
}
