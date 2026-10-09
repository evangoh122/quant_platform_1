import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../api/client';
import type { ChatResponse, SecCoverageItem, SecCoverageResponse } from '../api/types';
import { SymbolPicker } from '../components/SymbolPicker';
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
  const [selected, setSelected] = useState<string>('');
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
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

  const handleSelect = useCallback(
    (ticker: string) => {
      if (!ticker) {
        requestIdRef.current += 1;
        setSelected('');
        setResult(null);
        setError(null);
        setLoading(false);
        return;
      }
      const reqId = ++requestIdRef.current;
      setSelected(ticker);
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

  const secTool = result?.tool_calls.find((tc) => tc.name === 'search_sec_filings');
  const rawRows: Record<string, unknown>[] =
    secTool?.result && typeof secTool.result === 'object' && Array.isArray(secTool.result.rows)
      ? (secTool.result.rows as Record<string, unknown>[])
      : [];
  const secToolError =
    secTool?.result && typeof secTool.result === 'object' && typeof secTool.result.error === 'string'
      ? secTool.result.error
      : null;
  const firstRow = rawRows.length > 0 ? rawRows[0] : null;
  const firstRowError = firstRow && typeof firstRow.error === 'string' ? firstRow.error : null;
  const effectiveError = firstRowError ?? secToolError;
  const isNoCoverage = effectiveError === 'no_coverage';
  const noCoverageTicker = isNoCoverage
    ? String((firstRow && firstRow.ticker) ?? selected)
    : '';
  const isRetrievalUnavailable = effectiveError === 'retrieval_unavailable';
  const retrievalUnavailableMessage = isRetrievalUnavailable
    ? String((firstRow && firstRow.message) ?? 'SEC search is temporarily unavailable.')
    : '';
  const hasUnknownError =
    effectiveError !== null && effectiveError !== 'no_coverage' && effectiveError !== 'retrieval_unavailable';
  const unknownErrorMessage = hasUnknownError
    ? String((firstRow && firstRow.message) ?? effectiveError)
    : '';
  const isError = isNoCoverage || isRetrievalUnavailable || hasUnknownError;
  const rows = isError ? [] : rawRows;

  const useFallback = coverageStatus === 'unavailable';

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">SEC Filing Explorer</h1>

      {coverageStatus === 'loading' && <LoadingState label="Loading equities…" />}

      {useFallback && (
        <div className="rounded-md border border-warning-dim-30 bg-warning-dim px-3 py-2 text-sm text-warning-text">
          Equity coverage data is unavailable. Enter a ticker manually.
        </div>
      )}

      {!useFallback && coverageStatus === 'ok' && (
        <p className="text-sm text-[var(--text-secondary)]">
          {coverage.length} equit{coverage.length === 1 ? 'y' : 'ies'} with SEC filings
        </p>
      )}

      {coverageStatus !== 'loading' && (
        useFallback ? (
          <SymbolPicker
            value={selected}
            onChange={handleSelect}
            list="sec"
            label="Equity"
          />
        ) : (
          <SymbolPicker
            value={selected}
            onChange={handleSelect}
            secMode
            secCoverage={coverage}
            hasCoverage={selected ? coverage.some((c) => c.ticker === selected.toUpperCase()) : undefined}
            label="Equity"
          />
        )
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
                  <li key={i} className="rounded-md border border-[var(--border)] p-3">
                    {section && (
                      <div className="text-xs font-semibold text-[var(--text-muted)]">{section}</div>
                    )}
                    <p className="mt-1 text-sm text-[var(--text-secondary)]">
                      {text.slice(0, 320)}
                    </p>
                    {link && (
                      <a
                        href={link}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-1 inline-block text-xs text-[var(--accent)] underline hover:text-[var(--accent-bright)]"
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