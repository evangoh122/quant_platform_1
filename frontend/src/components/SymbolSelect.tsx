import symbols from '../data/symbols.json';

type SymbolList = 'market' | 'options' | 'sec';

const LISTS: Record<SymbolList, string[]> = {
  market: (symbols as { market: string[] }).market,
  options: (symbols as { options: string[] }).options,
  sec: (symbols as { sec: string[] }).sec,
};

/** Dropdown of companies that have data in the lakehouse (list generated from Unity Catalog). */
export function SymbolSelect({
  value,
  onChange,
  list = 'market',
}: {
  value: string;
  onChange: (symbol: string) => void;
  list?: SymbolList;
}) {
  const options = LISTS[list];
  const items = options.includes(value) ? options : [value, ...options];
  return (
    <select
      aria-label="Company"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-md border border-[var(--border)] px-3 py-1.5 text-sm bg-[var(--surface-raised)] text-[var(--text-primary)]"
    >
      {items.map((s) => (
        <option key={s} value={s}>
          {s}
        </option>
      ))}
    </select>
  );
}
