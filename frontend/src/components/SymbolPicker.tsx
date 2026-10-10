import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import symbols from '../data/symbols.json';
import { getRecentSymbols, pushRecentSymbol, getUrlSymbol, setUrlSymbol } from '../utils/symbolStorage';

type SymbolList = 'market' | 'options' | 'sec';

const QUICK_CHOICES = ['NVDA', 'AAPL', 'MSFT', 'AMD', 'SPY'] as const;
// Share-class suffixes (e.g. BRK.B) are part of the data-backed universe in symbols.json.
const TICKER_RE = /^[A-Z]{1,5}(\.[A-Z]{1,2})?$/;

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
  const valueRef = useRef(value);
  const [committedValue, setCommittedValue] = useState(value);

  const options = secMode
    ? (secCoverage ?? []).map((c) => c.ticker)
    : LISTS[list];

  const [recent, setRecent] = useState(() => getRecentSymbols());

  // Initialize from URL param once — lift to parent so the screen/API uses it
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    const urlSym = getUrlSymbol();
    if (urlSym && urlSym !== value) {
      const upper = urlSym.toUpperCase();
      if (TICKER_RE.test(upper)) {
        onChange(upper);
      }
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep query in sync with value
  useEffect(() => {
    setQuery(value);
    valueRef.current = value;
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
      setRecent(getRecentSymbols());
      setUrlSymbol(upper);
    },
    [onChange],
  );

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!open) {
      if (e.key === 'ArrowDown') {
        setOpen(true);
        e.preventDefault();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const trimmed = query.trim().toUpperCase();
        if (trimmed && TICKER_RE.test(trimmed)) {
          handleSelect(trimmed);
        } else {
          setOpen(true);
        }
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
      } else {
        const trimmed = query.trim().toUpperCase();
        if (trimmed && TICKER_RE.test(trimmed)) {
          handleSelect(trimmed);
        }
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
        <label className="text-sm text-[var(--text-muted)]">{label}</label>
        <div ref={containerRef} className="relative w-full max-w-xs">
          <div className="flex items-center rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface-elevated)]">
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
                // Normalize to current value on blur (read ref to avoid stale prop)
                setTimeout(() => {
                  setQuery(valueRef.current);
                  setOpen(false);
                }, 150);
              }}
              className="w-full bg-transparent px-3 py-1.5 text-sm text-[var(--text-primary)] outline-none"
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
                className="px-2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                ×
              </button>
            )}
          </div>
          {open && filtered.length > 0 && (
            <ul
              id="symbol-picker-listbox"
              role="listbox"
              className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-elevated)] text-sm shadow-lg"
            >
              {filtered.map((sym, i) => (
                <li
                  key={sym}
                  role="option"
                  aria-selected={sym === value.toUpperCase()}
                  className={`cursor-pointer px-3 py-1.5 ${
                    i === highlightIdx
                      ? 'bg-[var(--accent-dim)]'
                      : 'hover:bg-[var(--surface-raised)]'
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
            <div className="absolute z-10 mt-1 w-full rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-elevated)] px-3 py-2 text-sm shadow-lg">
              {TICKER_RE.test(query.trim().toUpperCase()) ? (
                <button
                  type="button"
                  className="w-full cursor-pointer text-left text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleSelect(query.trim().toUpperCase());
                  }}
                >
                  Submit {query.trim().toUpperCase()} — server will check coverage
                </button>
              ) : (
                <span className="text-[var(--text-muted)]">No matching symbols</span>
              )}
            </div>
          )}
        </div>

        {hasCoverage !== undefined && value && (
          <span
            className={`badge ${hasCoverage ? 'badge-green' : 'badge-muted'}`}
          >
            {hasCoverage ? 'Has data' : 'No coverage'}
          </span>
        )}
      </div>

      {showNoCoverage && (
        <p className="text-xs text-[var(--warning)]">
          {committedValue.toUpperCase()} is not in the {secMode ? 'SEC coverage' : list} dataset. Data may be unavailable.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-[var(--text-muted)]">Quick:</span>
        {QUICK_CHOICES.map((sym) => (
          <button
            key={sym}
            type="button"
            onClick={() => handleSelect(sym)}
            className={`rounded-[var(--radius-md)] px-2 py-0.5 text-xs font-medium transition-colors ${
              sym === value.toUpperCase()
                ? 'bg-[var(--accent-fill)] text-[var(--accent-ink)]'
                : 'bg-[var(--surface-raised)] text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)]'
            }`}
          >
            {sym}
          </button>
        ))}
        {recent.length > 0 && (
          <>
            <span className="ml-2 text-xs text-[var(--text-muted)]">Recent:</span>
            {recent
              .filter((s) => !QUICK_CHOICES.includes(s as (typeof QUICK_CHOICES)[number]))
              .slice(0, 4)
              .map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => handleSelect(sym)}
                  className={`rounded-[var(--radius-md)] px-2 py-0.5 text-xs font-medium transition-colors ${
                    sym === value.toUpperCase()
                      ? 'bg-[var(--accent-fill)] text-[var(--accent-ink)]'
                      : 'bg-[var(--surface-raised)] text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)]'
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