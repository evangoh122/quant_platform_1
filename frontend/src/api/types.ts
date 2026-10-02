// Mirror of api/schemas.py. Keep these in sync with the backend pydantic models.

export type FreshnessState = 'fresh' | 'stale' | 'empty' | 'unavailable';

export interface Freshness {
  state: FreshnessState;
  table: string;
  detail: string;
}

export interface Envelope<T> {
  data: T[];
  count: number;
  empty: boolean;
  source: string;
  freshness: Freshness;
}

export interface Signal {
  signal_id: string;
  symbol: string;
  direction: string;
  probability: number | null;
  prediction_ts: string;
  model_version: string;
  horizon: string;
  status: string;
  feature_snapshot_id: string | null;
}

export interface OHLCVFeature {
  symbol: string;
  feature_ts: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  vwap: number | null;
}

export interface OptionsFeature {
  symbol: string;
  feature_ts: string;
  expiry: string;
  atm_iv: number | null;
  skew: number | null;
  put_call_ratio: number | null;
  volume_anomaly: number | null;
}

export interface MarketSnapshot {
  symbol: string;
  ohlcv: Envelope<OHLCVFeature>;
  options: Envelope<OptionsFeature>;
}

export interface WatchlistItem {
  symbol: string;
  created_at: string;
}

export interface Order {
  order_id: string;
  symbol: string;
  side: string;
  quantity: number;
  notional: number;
  order_type: string;
  limit_price: number | null;
  status: string;
  signal_id: string | null;
  idempotency_key: string;
  created_at: string;
}

export interface Position {
  account_id: string;
  symbol: string;
  quantity: number;
  avg_cost: number;
  market_price: number | null;
  realized_pnl: number;
  unrealized_pnl: number;
  updated_at: string;
}

export interface Portfolio {
  positions: Envelope<Position>;
  orders: Envelope<Order>;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown> | null;
  ok: boolean;
}

export interface ChatRequest {
  message: string;
}

export interface ChatResponse {
  reply: string;
  tool_calls: ToolCall[];
  sources: Record<string, unknown>[];
  available: boolean;
  empty: boolean;
}

export interface DependencyStatus {
  name: string;
  ok: boolean;
  detail: string;
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  version: string;
  dependencies: DependencyStatus[];
  freshness: Freshness;
}

export interface AnalyticsItem {
  metric: string;
  value: number | null;
  detail: string;
}

export interface AnalyticsResponse {
  model_performance: Envelope<AnalyticsItem>;
  agent_activity: Envelope<AnalyticsItem>;
  latency: Envelope<AnalyticsItem>;
  stream_freshness: Envelope<AnalyticsItem>;
}

export interface OrderIntentRequest {
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  order_type: 'MARKET' | 'LIMIT';
  limit_price?: number;
  signal_id?: string;
  idempotency_key?: string;
}

export interface OrderIntentResult {
  order_id: string;
  status: string;
  idempotency_key: string;
}

export interface OrderActionResult {
  order_id: string;
  status: string;
  ok: boolean;
  broker_order_id: string | null;
  reason: string | null;
  risk: Record<string, unknown> | null;
}
