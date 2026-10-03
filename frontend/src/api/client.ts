import type {
  AnalyticsResponse,
  ChatRequest,
  ChatResponse,
  Envelope,
  HealthResponse,
  MarketSnapshot,
  OrderActionResult,
  OrderIntentRequest,
  OrderIntentResult,
  Portfolio,
  Signal,
  WatchlistItem,
} from './types';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}

export const api = {
  health: (): Promise<HealthResponse> => request<HealthResponse>('/api/health'),
  signals: (symbol?: string): Promise<Envelope<Signal>> => {
    const query = symbol ? `?symbol=${encodeURIComponent(symbol)}` : '';
    return request<Envelope<Signal>>(`/api/signals${query}`);
  },
  market: (symbol: string): Promise<MarketSnapshot> =>
    request<MarketSnapshot>(`/api/market/${encodeURIComponent(symbol)}`),
  chat: (message: string): Promise<ChatResponse> =>
    post<ChatResponse>('/api/agent/chat', { message } satisfies ChatRequest),
  watchlists: (): Promise<Envelope<WatchlistItem>> =>
    request<Envelope<WatchlistItem>>('/api/watchlists'),
  addWatchlist: (symbol: string): Promise<WatchlistItem> =>
    post<WatchlistItem>('/api/watchlists', { symbol }),
  portfolio: (): Promise<Portfolio> => request<Portfolio>('/api/portfolio'),
  analytics: (): Promise<AnalyticsResponse> =>
    request<AnalyticsResponse>('/api/analytics'),
  createIntent: (body: OrderIntentRequest): Promise<OrderIntentResult> =>
    post<OrderIntentResult>('/api/orders/intents', body),
  approveOrder: (orderId: string): Promise<OrderActionResult> =>
    post<OrderActionResult>(`/api/orders/${encodeURIComponent(orderId)}/approve`, {}),
  cancelOrder: (orderId: string): Promise<OrderActionResult> =>
    post<OrderActionResult>(`/api/orders/${encodeURIComponent(orderId)}/cancel`, {}),
};
