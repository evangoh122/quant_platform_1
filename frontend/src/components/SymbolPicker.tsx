import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import symbols from '../data/symbols.json';
import { getRecentSymbols, pushRecentSymbol, getUrlSymbol, setUrlSymbol } from '../utils/symbolStorage';

type SymbolList = 'market' | 'options' | 'sec';

const QUICK_CHOICES = ['NVDA', 'AAPL', 'MSFT', 'AMD', 'SPY'] as const;
const TICKER_RE = /^[A-Z]{1,5}$/;

const LISTS: Record<SymbolList, string[]> = {
  market: (symbols as { market: string[] }).market,
  options: (symbols as { options: string[] }).options,
  sec: (symbols as { sec: string[] }).sec,
};

interface SymbolPickerProps {
  value: string;
  onChange: (symbol: string) => void;
  list?: SymbolList;
  /** When true, coverage/options come from secCoverage instead of symbols.json */
  secMode?: boolean;
  /** SEC coverage items (only used when secMode=true) */
  secCoverage?: { ticker: string; n_filings: number; last_filed: string | null }[];
  /** Whether the current symbol has coverage in the active dataset */
  hasCoverage?: boolean;
  /** Label shown next to the picker */
  label?: string;
}

export function SymbolPicker({
  value,
  onChange,
  list = 'market',
  secMode = false,
  secCoverage,
  hasCoverage,
  label = 'Company',
}: SymbolPickerProps) {
  const [query, setQuery] = useState(value);
  const [open, setOpen] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const initializedRef = useRef(false);
  const [committedValue, setCommittedValue] = useState(value);

  const options = secMode
    ? (secCoverage ?? []).map((c) => c.ticker)
    : LISTS[list];

  const recent = useMemo(() => getRecentSymbols(), []);

  // Initialize from URL param once — lift to parent so the screen/API uses it
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    const urlSym = getUrlSymbol();
    if (urlSym && urlSym !== value) {
      const upper = urlSym.toUpperCase();
      const isValid = options.includes(upper) || LISTS.market.includes(upper);
      if (isValid) {
        onChange(upper);
      }
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep query in sync with value
  useEffect(() => {
    setQuery(value);
    if (value) setCommittedValue(value);
  }, [value]);

  const filtered = useMemo(() => {
    const q = query.trim().toUpperCase();
    if (!q) return options;
    return options.filter((s) => s.includes(q));
  }, [options, query]);

  const handleSelect = useCallback(
    (symbol: string) => {
      const upper = symbol.toUpperCase();
      onChange(upper);
      setQuery(upper);
      setCommittedValue(upper);
      setOpen(false);
      pushRecentSymbol(upper);
      setUrlSymbol(upper);
    },
    [onChange],
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
        handleSelect(filtered[highlightIdx]);
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

  const inList = options.includes(committedValue.toUpperCase());
  const showNoCoverage = committedValue && !inList;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <label className="text-sm text-slate-600 dark:text-slate-400">{label}</label>
        <div ref={containerRef} className="relative w-full max-w-xs">
          <div className="flex items-center rounded-md border border-slate-300 dark:border-slate-700 dark:bg-slate-900">
            <input
              ref={inputRef}
              type="text"
              role="combobox"
              aria-expanded={open}
              aria-controls="symbol-picker-listbox"
              aria-autocomplete="list"
              aria-label="Select symbol"
              value={query}
              onChange={(e) => {
                const val = e.target.value.toUpperCase();
                setQuery(val);
                setOpen(true);
              }}
              onFocus={() => setOpen(true)}
              onKeyDown={handleKeyDown}
              onBlur={() => {
                // Normalize to current value on blur
                setTimeout(() => {
                  setQuery(value);
                  setOpen(false);
                }, 150);
              }}
              className="w-full bg-transparent px-3 py-1.5 text-sm outline-none"
              placeholder="Type a symbol…"
            />
            {query && (
              <button
                type="button"
                aria-label="Clear"
                onClick={() => {
                  setQuery('');
                  onChange('');
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
              id="symbol-picker-listbox"
              role="listbox"
              className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md border border-slate-300 bg-white text-sm shadow-lg dark:border-slate-700 dark:bg-slate-900"
            >
              {filtered.map((sym, i) => (
                <li
                  key={sym}
                  role="option"
                  aria-selected={sym === value.toUpperCase()}
                  className={`cursor-pointer px-3 py-1.5 ${
                    i === highlightIdx
                      ? 'bg-slate-100 dark:bg-slate-800'
                      : 'hover:bg-slate-50 dark:hover:bg-slate-800/50'
                  }`}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleSelect(sym);
                  }}
                  onMouseEnter={() => setHighlightIdx(i)}
                >
                  {sym}
                </li>
              ))}
            </ul>
          )}
          {open && filtered.length === 0 && (
            <div className="absolute z-10 mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-lg dark:border-slate-700 dark:bg-slate-900">
              {TICKER_RE.test(query.trim().toUpperCase()) ? (
                <button
                  type="button"
                  className="w-full cursor-pointer text-left text-slate-700 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleSelect(query.trim().toUpperCase());
                  }}
                >
                  Submit {query.trim().toUpperCase()} — server will check coverage
                </button>
              ) : (
                <span className="text-slate-500 dark:text-slate-400">No matching symbols</span>
              )}
            </div>
          )}
        </div>

        {hasCoverage !== undefined && value && (
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${
              hasCoverage
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
            }`}
          >
            {hasCoverage ? 'Has data' : 'No coverage'}
          </span>
        )}
      </div>

      {showNoCoverage && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          {committedValue.toUpperCase()} is not in the {secMode ? 'SEC coverage' : list} dataset. Data may be unavailable.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-slate-500 dark:text-slate-400">Quick:</span>
        {QUICK_CHOICES.map((sym) => (
          <button
            key={sym}
            type="button"
            onClick={() => handleSelect(sym)}
            className={`rounded-md px-2 py-0.5 text-xs font-medium transition-colors ${
              sym === value.toUpperCase()
                ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
            }`}
          >
            {sym}
          </button>
        ))}
        {recent.length > 0 && (
          <>
            <span className="ml-2 text-xs text-slate-500 dark:text-slate-400">Recent:</span>
            {recent
              .filter((s) => !QUICK_CHOICES.includes(s as (typeof QUICK_CHOICES)[number]))
              .slice(0, 4)
              .map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => handleSelect(sym)}
                  className={`rounded-md px-2 py-0.5 text-xs font-medium transition-colors ${
                    sym === value.toUpperCase()
                      ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                      : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                  }`}
                >
                  {sym}
                </button>
              ))}
          </>
        )}
      </div>
    </div>
  );
}