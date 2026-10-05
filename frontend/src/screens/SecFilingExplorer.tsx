import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { api } from '../api/client';
import type { ChatResponse, SecCoverageItem, SecCoverageResponse } from '../api/types';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';

const LINK_KEYS = ['edgar_url', 'url', 'source_url', 'href'];

function rowLink(row: Record<string, unknown>): string | null {
  for (const key of LINK_KEYS) {
    const value = row[key];
    if (typeof value === 'string' && value.length > 0) return value;
  }
  return null;
}

function formatDate(iso: string | null): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

export function SecFilingExplorer() {
  const [coverage, setCoverage] = useState<SecCoverageItem[]>([]);
  const [coverageStatus, setCoverageStatus] = useState<'loading' | 'ok' | 'unavailable'>('loading');
  const [input, setInput] = useState('');
  const [selected, setSelected] = useState<string>('');
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(0);
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    api
      .secCoverage()
      .then((res: SecCoverageResponse) => {
        if (cancelled) return;
        if (res.status === 'unavailable') {
          setCoverageStatus('unavailable');
        } else {
          setCoverage(res.data);
          setCoverageStatus('ok');
        }
      })
      .catch(() => {
        if (cancelled) return;
        setCoverageStatus('unavailable');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toUpperCase();
    if (!q) return coverage;
    return coverage.filter((item) => item.ticker.toUpperCase().includes(q));
  }, [coverage, query]);

  const handleSelect = useCallback(
    (ticker: string) => {
      const reqId = ++requestIdRef.current;
      setSelected(ticker);
      setQuery(ticker);
      setOpen(false);
      setResult(null);
      setError(null);
      setLoading(true);
      api
        .chat(`search SEC filings for ${ticker}`)
        .then((res) => {
          if (reqId === requestIdRef.current) {
            setResult(res);
          }
        })
        .catch((e) => {
          if (reqId === requestIdRef.current) {
            setError(e instanceof Error ? e.message : String(e));
          }
        })
        .finally(() => {
          if (reqId === requestIdRef.current) {
            setLoading(false);
          }
        });
    },
    [],
  );

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') {
        setOpen(true);
        e.preventDefault();
      }
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filtered[highlightIdx]) {
        handleSelect(filtered[highlightIdx].ticker);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  }

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    setHighlightIdx(0);
  }, [query]);

  const secTool = result?.tool_calls.find((tc) => tc.name === 'search_sec_filings');
  const rawRows: Record<string, unknown>[] =
    secTool?.result && typeof secTool.result === 'object' && Array.isArray(secTool.result.rows)
      ? (secTool.result.rows as Record<string, unknown>[])
      : [];
  const isNoCoverage = rawRows.length > 0 && rawRows[0]?.error === 'no_coverage';
  const noCoverageTicker = isNoCoverage ? String(rawRows[0].ticker ?? selected) : '';
  const isRetrievalUnavailable = rawRows.length > 0 && rawRows[0]?.error === 'retrieval_unavailable';
  const retrievalUnavailableMessage = isRetrievalUnavailable
    ? String(rawRows[0].message ?? 'SEC search is temporarily unavailable.')
    : '';
  const hasUnknownError =
    rawRows.length > 0 &&
    typeof rawRows[0]?.error === 'string' &&
    rawRows[0].error !== 'no_coverage' &&
    rawRows[0].error !== 'retrieval_unavailable';
  const unknownErrorMessage = hasUnknownError
    ? String(rawRows[0].message ?? rawRows[0].error)
    : '';
  const isError = isNoCoverage || isRetrievalUnavailable || hasUnknownError;
  const rows = isError ? [] : rawRows;

  const useFallback = coverageStatus === 'unavailable';

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">SEC Filing Explorer</h1>

      {coverageStatus === 'loading' && <LoadingState label="Loading equities…" />}

      {useFallback && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200">
          Equity coverage data is unavailable. Enter a ticker manually.
        </div>
      )}

      {!useFallback && coverageStatus === 'ok' && (
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {coverage.length} equit{coverage.length === 1 ? 'y' : 'ies'} with SEC filings
        </p>
      )}

      {useFallback ? (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const sym = input.trim().toUpperCase();
            if (!sym) return;
            handleSelect(sym);
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
            placeholder="Search filings for a symbol (e.g. NVDA)"
          />
          <button
            type="submit"
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-slate-100 dark:text-slate-900"
          >
            Search
          </button>
        </form>
      ) : (
        <div ref={containerRef} className="relative w-full max-w-xs">
          <div className="flex items-center rounded-md border border-slate-300 dark:border-slate-700 dark:bg-slate-900">
            <input
              ref={inputRef}
              type="text"
              role="combobox"
              aria-expanded={open}
              aria-controls="sec-equity-listbox"
              aria-autocomplete="list"
              aria-label="Select equity"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setOpen(true);
                if (selected && e.target.value !== selected) {
                  setSelected('');
                }
              }}
              onFocus={() => setOpen(true)}
              onKeyDown={handleKeyDown}
              className="w-full bg-transparent px-3 py-1.5 text-sm outline-none"
              placeholder="Filter by ticker…"
            />
            {selected && (
              <button
                type="button"
                aria-label="Clear selection"
                onClick={() => {
                  setSelected('');
                  setQuery('');
                  setResult(null);
                  inputRef.current?.focus();
                }}
                className="px-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                ×
              </button>
            )}
          </div>
          {open && filtered.length > 0 && (
            <ul
              id="sec-equity-listbox"
              role="listbox"
              className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md border border-slate-300 bg-white text-sm shadow-lg dark:border-slate-700 dark:bg-slate-900"
            >
              {filtered.map((item, i) => (
                <li
                  key={item.ticker}
                  role="option"
                  aria-selected={item.ticker === selected}
                  className={`flex cursor-pointer items-center justify-between px-3 py-1.5 ${
                    i === highlightIdx
                      ? 'bg-slate-100 dark:bg-slate-800'
                      : 'hover:bg-slate-50 dark:hover:bg-slate-800/50'
                  }`}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleSelect(item.ticker);
                  }}
                  onMouseEnter={() => setHighlightIdx(i)}
                >
                  <span className="font-medium">{item.ticker}</span>
                  <span className="ml-2 text-xs text-slate-500 dark:text-slate-400">
                    {item.n_filings} filing{item.n_filings !== 1 ? 's' : ''}
                    {item.last_filed && ` · ${formatDate(item.last_filed)}`}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {open && filtered.length === 0 && (
            <div className="absolute z-10 mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-500 shadow-lg dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
              No matching tickers
            </div>
          )}
        </div>
      )}

      {loading && <LoadingState />}
      {error && <ErrorState message={error} />}

      {!loading && !error && result === null && !selected && (
        <EmptyState title="Select a ticker to see its SEC filing sections" />
      )}

      {!loading && !error && result !== null && isNoCoverage && (
        <EmptyState title={`No SEC filings have been processed for ${noCoverageTicker} yet.`} />
      )}

      {!loading && !error && result !== null && isRetrievalUnavailable && (
        <ErrorState
          message={retrievalUnavailableMessage}
          onRetry={() => handleSelect(selected)}
        />
      )}

      {!loading && !error && result !== null && hasUnknownError && (
        <ErrorState message={unknownErrorMessage} />
      )}

      {!loading && !error && result !== null && !isNoCoverage && !isRetrievalUnavailable && !hasUnknownError && (
        <Card title="Extracted Sections & Sources">
          {rows.length === 0 ? (
            <EmptyState title="No SEC filing sections found for this search" />
          ) : (
            <ul className="space-y-2">
              {rows.map((row, i) => {
                const link = rowLink(row);
                const text = typeof row.chunk_text === 'string' ? row.chunk_text : '';
                const section =
                  typeof row.section === 'string'
                    ? row.section
                    : typeof row.filing_section === 'string'
                      ? row.filing_section
                      : '';
                return (
                  <li key={i} className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
                    {section && (
                      <div className="text-xs font-semibold text-slate-500">{section}</div>
                    )}
                    <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">
                      {text.slice(0, 320)}
                    </p>
                    {link && (
                      <a
                        href={link}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-1 inline-block text-xs text-blue-600 underline dark:text-blue-400"
                      >
                        View source
                      </a>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      )}
    </div>
  );
}