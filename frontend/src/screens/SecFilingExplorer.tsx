import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { api } from '../api/client';
import type { ChatResponse, SecCoverageItem, SecCoverageResponse } from '../api/types';
import { SymbolPicker } from '../components/SymbolPicker';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { ChartFrame } from '../components/charts';

const LINK_KEYS = ['edgar_url', 'url', 'source_url', 'href'];
const DEFAULT_TOP_N = 25;

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

interface CoverageChartProps {
  items: SecCoverageItem[];
  defaultLimit?: number;
}

function CoverageChart({ items, defaultLimit = DEFAULT_TOP_N }: CoverageChartProps) {
  const [showAll, setShowAll] = useState(false);

  const sorted = useMemo(
    () => [...items].sort((a, b) => b.n_chunks - a.n_chunks),
    [items],
  );

  const displayed = showAll ? sorted : sorted.slice(0, defaultLimit);
  const totalTickers = items.length;
  const tickersWithChunks = items.filter((c) => c.n_chunks > 0).length;
  const totalChunks = items.reduce((s, c) => s + c.n_chunks, 0);

  if (sorted.length === 0) {
    return <EmptyState title="No SEC coverage data" detail="No ticker coverage data is available." />;
  }

  const barHeight = 18;
  const gap = 4;
  const labelWidth = 50;
  const chartWidth = 500;
  const barAreaWidth = chartWidth - labelWidth - 70;
  const totalHeight = displayed.length * (barHeight + gap) + 30;

  const maxChunks = Math.max(...displayed.map((c) => c.n_chunks), 1);
  const chunkScale = (v: number) => (v / maxChunks) * barAreaWidth;

  const tableData = {
    headers: ['Ticker', 'Chunks', 'Filings', 'First Filed', 'Last Filed'],
    rows: displayed.map((c) => [
      c.ticker,
      c.n_chunks,
      c.n_filings,
      formatDate(c.first_filed),
      formatDate(c.last_filed),
    ]),
  };

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
        <span className="font-medium text-slate-700 dark:text-slate-200">
          {tickersWithChunks} / {totalTickers} tickers with chunks
        </span>
        <span className="text-slate-500 dark:text-slate-400">
          {totalChunks.toLocaleString()} total chunks
        </span>
        {sorted.length > defaultLimit && (
          <button
            type="button"
            onClick={() => setShowAll(!showAll)}
            className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            {showAll ? `Show top ${defaultLimit}` : `Show all ${sorted.length}`}
          </button>
        )}
      </div>

      <ChartFrame
        title={`SEC Coverage — ${showAll ? 'All' : `Top ${Math.min(defaultLimit, sorted.length)}`} Tickers`}
        caption="gold_sec_coverage · n_chunks per ticker"
        tableData={tableData}
        width={chartWidth}
        height={totalHeight}
        ariaLabel="SEC coverage chart showing chunks per ticker"
      >
        {displayed.map((item, i) => {
          const y = i * (barHeight + gap) + 10;
          const barW = chunkScale(item.n_chunks);

          return (
            <g key={item.ticker}>
              <text
                x={labelWidth - 4}
                y={y + barHeight / 2 + 4}
                textAnchor="end"
                className="fill-slate-600 dark:fill-slate-300"
                style={{ fontSize: 9, fontWeight: 500 }}
              >
                {item.ticker}
              </text>
              <rect
                x={labelWidth}
                y={y}
                width={Math.max(barW, 1)}
                height={barHeight}
                rx={2}
                fill="var(--accent, #3b82f6)"
                opacity={0.75}
              >
                <title>{`${item.ticker}: ${item.n_chunks.toLocaleString()} chunks, ${item.n_filings} filings`}</title>
              </rect>
              <text
                x={labelWidth + barW + 4}
                y={y + barHeight / 2 + 4}
                className="fill-slate-500 dark:fill-slate-400"
                style={{ fontSize: 9 }}
              >
                {item.n_chunks.toLocaleString()}
              </text>
            </g>
          );
        })}
      </ChartFrame>
    </div>
  );
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
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200">
          Equity coverage data is unavailable. Enter a ticker manually.
        </div>
      )}

      {!useFallback && coverageStatus === 'ok' && (
        <p className="text-sm text-slate-600 dark:text-slate-400">
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

      {coverageStatus === 'ok' && coverage.length > 0 && (
        <Card
          title="SEC Research Coverage"
          subtitle="gold_sec_coverage · chunks and filings per ticker"
        >
          <CoverageChart items={coverage} />
        </Card>
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