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
  event_date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  vwap: number | null;
  price_basis: string;
}

export interface OptionsFeature {
  symbol: string;
  feature_ts: string;
  put_volume: number | null;
  call_volume: number | null;
  put_call_ratio: number | null;
  iv_atm: number | null;
  iv_25d_put: number | null;
  iv_25d_call: number | null;
  iv_skew: number | null;
  iv_term_slope: number | null;
  avg_spread_pct: number | null;
  volume_anomaly_zscore: number | null;
  oi_concentration: number | null;
  net_delta_exposure: number | null;
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
  latency_ms: number | null;
  last_error: string | null;
  last_ok_at: number | null;
  circuit_breaker_state: string | null;
}

export interface StartupStage {
  name: string;
  elapsed_ms: number;
  ok: boolean;
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  version: string;
  dependencies: DependencyStatus[];
  freshness: Freshness;
  role_cache_size: number;
  startup: StartupStage[];
}

export interface TraceEvent {
  name: string;
  elapsed_ms: number;
  ok: boolean;
  error: string | null;
  extra: Record<string, unknown>;
  ts: number;
}

export interface HealthTraceResponse {
  recent: TraceEvent[];
  slow: TraceEvent[];
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

export interface SecCoverageItem {
  ticker: string;
  cik: string;
  n_filings: number;
  n_chunks: number;
  first_filed: string | null;
  last_filed: string | null;
}

export interface SecCoverageResponse {
  data: SecCoverageItem[];
  count: number;
  status: 'ok' | 'unavailable';
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
