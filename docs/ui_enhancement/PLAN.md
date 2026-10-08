# UI enhancement implementation plan

This is the implementation plan for the first delivery slice in
`OWNER_PLAN.md`. It is a planning artifact; it does not implement the UI.
Build rounds are strictly sequential: MiMo completes one request, Kimi
validates its exact commit, and Codex performs final validation before the next
request starts. A handoff file is not edited by two active rounds at once.

## Verified wire contracts

The backend source of truth is `api/schemas.py` and the route behavior is in
`api/routes/{agent_chat,analytics,health,market,signals,portfolio,orders,watchlists}.py`.
The frontend mirror is `frontend/src/api/types.ts`; the analytics mirror is
currently incomplete and must be corrected in the slice that consumes it.

### Shared envelope

Every list-like backend response uses:

```ts
{
  data: T[];
  count: number;
  empty: boolean;
  source: string;
  freshness: {
    state: 'fresh' | 'stale' | 'empty' | 'unavailable';
    table: string;
    detail: string;
  };
}
```

`empty` and `freshness.state` are authoritative. An empty or unavailable
envelope must not be converted into a measured zero.

### Existing API shapes used by the new UI

| Endpoint / component | Exact response consumed | Verified source and notes |
| --- | --- | --- |
| `GET /api/health` → `StatusBanner`, `SystemHealth` | `{ status: 'ok'\|'degraded', version: string, dependencies: DependencyStatus[], freshness: Freshness, role_cache_size: number, startup: StartupStage[] }`; each dependency is `{ name, ok, detail, latency_ms: number\|null, last_error: string\|null, last_ok_at: number\|null, circuit_breaker_state: string\|null }` | `api/schemas.py:195-214`, `api/routes/health.py`; current app detects Lakebase by `name === 'lakebase'` and `!ok` or breaker `open`. |
| `GET /api/health/trace` → health evidence | `{ recent: TraceEvent[], slow: TraceEvent[] }`; a trace event is `{ name, elapsed_ms, ok, error: string\|null, extra: Record<string, unknown>, ts: number }` | `api/schemas.py:216-221`, `api/routes/health.py`; `error` is available to the current UI but must be rendered as a safe status, not raw exception text. |
| `GET /api/market/{symbol}` → `MarketDashboard`, `OptionsAnalytics`, `SymbolPicker` coverage | `{ symbol: string, ohlcv: Envelope<OHLCVFeature>, options: Envelope<OptionsFeature> }`; OHLCV rows are `{ symbol, event_date, open, high, low, close, volume, vwap, price_basis }`; options rows are `{ symbol, feature_ts, put_volume, call_volume, put_call_ratio, iv_atm, iv_25d_put, iv_25d_call, iv_skew, iv_term_slope, avg_spread_pct, volume_anomaly_zscore, oi_concentration, net_delta_exposure }` | `api/schemas.py:60-89`, `api/routes/market.py`; chart data comes only from `ohlcv.data`, sorted by `event_date`. |
| `GET /api/signals` → `SignalExplorer` | `Envelope<Signal>`; a signal is `{ signal_id, symbol, direction, probability: number\|null, prediction_ts, model_version, horizon, status, feature_snapshot_id: string\|null }` | `api/schemas.py:44-58`, `api/routes/signals.py`; published baseline metadata is product copy, not a new response field. |
| `POST /api/agent/chat` → agent conversation/evidence | `{ reply: string, tool_calls: ToolCall[], sources: Record<string, unknown>[], available: boolean, empty: boolean }`; each tool call is `{ name: string, arguments: Record<string, unknown>, result: Record<string, unknown>\|null, ok: boolean }` | `api/schemas.py:126-143`, `api/routes/agent_chat.py`, `agent/runtime.py:529-581`. The serialized response has no `trace_id`, stage list, ticker field, or top-level as-of field. |
| Agent retrieval result inside `tool_calls[].result` | `get_latest_signal` returns a signal-shaped object or `{ status: 'no_signals_published' }`; market/options tools return `{ rows: Record<string, unknown>[] }`; `search_sec_filings` returns `{ rows: SecRow[] }`. `SecRow` is `{ chunk_id, chunk_text, accession_number, form_type, accepted_ts, source_url, ticker, section, chunk_index, similarity, distance, rerank_score, retrieval_mode, _warning? }`. Unavailable retrieval is a row such as `{ error: 'retrieval_unavailable', message, ticker, reason? }`. | `agent/runtime.py:108-139`, `agent/tools_retrieval.py:87-219`. The runtime's `sources[]` is narrower: `{ tool, chunk_id, accession, form_type, section }`. Evidence cards must use the nested result rows for accepted timestamp, URL, and retrieval mode. |
| Agent write result inside `tool_calls[].result` | `save_research_note` returns `{ note_id, symbol, status: 'saved', replay?: true }`; `add_to_watchlist` returns `{ watchlist_id, symbol, status: 'added' }`. Failed calls are `{ error: 'execution_failed' }` with `ok: false`. | `agent/tools_write.py:188-279`, `agent/runtime.py:529-548`. A write is not authorized merely because the model proposed it; the request authorization is backend-controlled and the UI must show failures honestly. |
| `GET /api/analytics` → `ActivityAnalytics` (later B) | `AnalyticsResponse` has seven envelopes: `model_performance` and `latency` and `stream_freshness` contain `AnalyticsItem[]`, where each item is `{ metric: string, value: number\|null, detail: string }`; `agent_activity` uses the same item shape; `watchlist_changes`, `order_funnel`, and `usage_daily` contain `Record<string, unknown>[]`. Every section still has the shared envelope fields. | `api/schemas.py:223-232`, `api/routes/analytics.py:13-85`. `frontend/src/api/types.ts:165-170` currently declares only four sections and must be extended before B. |
| `GET /api/portfolio` → existing operations screen | `{ positions: Envelope<Position>, orders: Envelope<Order> }`; positions and orders retain the fields in `frontend/src/api/types.ts`. | `api/schemas.py:91-124`, `api/routes/portfolio.py`; shell work must preserve this route and behavior. |
| `GET /api/watchlists` / writes → existing operations and agent tour | GET is `Envelope<WatchlistItem>`; POST returns `{ symbol, created_at: string }` according to `WatchlistItem`, although the internal write tool also produces `watchlist_id`/`status` before route mapping. | `api/routes/watchlists.py:24-59`; do not display internal write-tool fields as if they were the endpoint contract. |
| Orders → existing order screen | Intent result `{ order_id, status, idempotency_key }`; action result `{ order_id, status, ok, broker_order_id: string\|null, reason: string\|null, risk: Record<string, unknown>\|null }`. | `api/routes/orders.py:20-34`, `api/schemas.py:235-258`; do not broaden the agent tool surface to orders. |

The redesign must not add a fake trace ID or simulated timing to the agent
response. `ExecutionTrace` can show stages supported by observed calls:
pending before submission, running while submitting, complete/failed after a
tool call, and skipped for stages not represented by the response. It must not
claim unobserved model/retrieval phases. If a future backend adds trace data,
that is a separate contract change.

## Slice order and ownership

| Round | Scope | Active ownership | Handoff / dependency |
| --- | --- | --- | --- |
| A1 | Design tokens, state primitives, shell, navigation, route labels, global status banner | `frontend/src/App.tsx`, `frontend/src/index.css`, `frontend/src/layout/**`, `frontend/src/components/states/**`, shell/navigation tests | Establishes the navigation IDs and `data-tour` shell targets used by A2. Existing screen components remain API-compatible. |
| A2 | Coach marks and three tours | `frontend/src/components/tours/**`, `frontend/src/components/tours.test.tsx`, tour host wiring in the shell handoff | Consumes A1's navigation targets; no edits to the reference UI or disclaimer code. |
| A3 | Platform Overview and Architecture & Tests | `frontend/src/screens/PlatformOverview.tsx`, `frontend/src/screens/ArchitectureEvidence.tsx`, overview/architecture tests, static rubric content | Uses A1 navigation slots and A2's tour host targets. Static snapshot numbers are labelled `Verified snapshot: 2026-10-05`. |
| A4 | Research Agent redesign, execution trace, evidence/tool cards | `frontend/src/screens/ResearchAgent.tsx`, `frontend/src/components/evidence/**`, `frontend/src/components/ExecutionTrace.tsx`, agent tests, narrowed agent API types/helpers | Consumes the verified ChatResponse shape above; no API route change and no XBRL/Polygon/graph UI. |
| A5 | SymbolPicker and one modest market chart | `frontend/src/components/SymbolPicker.tsx`, `frontend/src/screens/MarketDashboard.tsx`, `frontend/src/screens/OptionsAnalytics.tsx`, `frontend/src/screens/SecFilingExplorer.tsx`, picker/chart tests, URL/local-storage helpers | Replaces `SymbolSelect` usage without duplicating `symbols.json`; agent symbol scope is integrated only through A4's existing screen handoff. |

The rounds are not parallelizable because A2 depends on A1 shell targets, A3
depends on navigation destinations, and A5 touches existing market consumers.
When a handoff file must be changed, the preceding round must be committed
and checked before the next round begins; no two MiMo agents edit that file at
the same time.

## Cross-cutting acceptance rules

- Preserve React 18, Vite, Tailwind, all existing API paths, and the current
  internal screen behavior.
- Use solid surfaces, borders, focus-visible rings, semantic headings and
  controls, keyboard operation, and layouts that work at 360px.
- Do not import DuckDB, LangGraph, React Flow, review-queue APIs, old backend
  services, or the 72KB workbench `App.tsx`.
- Keep the signal copy explicit: baseline model
  `baseline-logreg-v0-2026-10-05`, hold-out AUC 0.47, pipeline demonstration,
  no edge claimed. Never present it as a validated trading signal or expose an
  arbitrary confidence score.
- Empty, stale, partial, and unavailable states remain distinguishable; the
  UI never turns an empty analytics envelope into `0`.
- Each BUILD request must require these commands:

  `cd frontend && npm ci && npm test -- --run && npx tsc --noEmit && npm run build`

- Each BUILD request must require LF line endings, no edits to
  `.agents/dispatch.sh`, a commit, and the MiMo completion report defined in
  `AGENTS.md`. Kimi and Codex must validate the resulting exact commit with
  file:line evidence.
