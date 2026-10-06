const RECENT_KEY = 'qp_recent_symbols';
const MAX_RECENT = 8;

export function getRecentSymbols(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((s): s is string => typeof s === 'string') : [];
  } catch {
    return [];
  }
}

export function pushRecentSymbol(symbol: string): void {
  try {
    const upper = symbol.toUpperCase();
    const recent = getRecentSymbols().filter((s) => s !== upper);
    recent.unshift(upper);
    localStorage.setItem(RECENT_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)));
  } catch {
    // localStorage unavailable (e.g. jsdom in tests)
  }
}

export function getUrlSymbol(): string | null {
  const params = new URLSearchParams(window.location.search);
  const sym = params.get('symbol');
  return sym ? sym.toUpperCase() : null;
}

export function setUrlSymbol(symbol: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set('symbol', symbol.toUpperCase());
  window.history.replaceState(null, '', url.toString());
}