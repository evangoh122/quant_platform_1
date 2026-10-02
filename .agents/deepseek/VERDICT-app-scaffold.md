# VERDICT: app-scaffold — DeepSeek (Builder)

**Status:** APPROVED (builder self-verdict — independent Codex/Claude validation still required per PROTOCOL; a builder verdict is not the gate)
**Round:** 1
**Branch:** `slice/app-scaffold`; `main` untouched

Turned the repo from a collection of Python packages into an application: a
FastAPI backend under `api/`, a React + TypeScript + Tailwind frontend under
`frontend/`, Databricks App packaging, and deployment/structure docs. The
inherited `api/services/` / `api/models/` are imported (never edited); `agent/`
and `db/` are imported (never edited).

## Routes implemented (exactly the §10.2 table)

| Route | Method | Reads/writes |
| :-- | :-- | :-- |
| `/api/health` | GET | dependency + freshness status |
| `/api/signals` | GET | `gold_trading_signals` (Delta) |
| `/api/market/{symbol}` | GET | `gold_ohlcv_features`, `gold_options_features` |
| `/api/agent/chat` | POST | agent runtime (deterministic tool dispatch) |
| `/api/watchlists` | GET, POST | Lakebase `watchlists` |
| `/api/orders/intents` | POST | Lakebase `orders` (`PENDING_APPROVAL`) |
| `/api/orders/{id}/approve` | POST | `record_approval` + `approve_and_place_paper_order` |
| `/api/orders/{id}/cancel` | POST | `cancel_paper_order` (execution bridge) |
| `/api/portfolio` | GET | Lakebase `positions`, `orders` |
| `/api/analytics` | GET | analytics tables (empty envelopes) |

The approval route records a durable approval with the **authenticated**
principal (`deps.get_current_user`) and then delegates to
`agent.tools_write.approve_and_place_paper_order(order_id)` — whose public
signature accepts only the order id, so risk state is never overridable.

## Screens created (frontend/, 8 rubric screens)

1. Market Dashboard — OHLCV stat tiles, freshness badge, features table.
2. Signal Explorer — ranked signals (direction/probability/model).
3. Options Analytics — chain metrics (IV/skew/P/C/volume anomaly).
4. SEC Filing Explorer — section search + extracted events + source links.
5. AI Research Agent — chat with visible tool-call/evidence blocks.
6. IBKR Paper Portfolio — positions, open orders, fills/P&L.
7. Order Approval Drawer — order detail, signal age, approve/reject with
   risk-check result surfaced after approval.
8. Analytics / System Health — dependency status + model/agent/latency/stream
   sections.

Shared typed API client (`src/api/client.ts` + `src/api/types.ts`, no `any`),
and components (`Card`, `Table`, `StatTile`, `EmptyState`, `ErrorState`,
`LoadingState`, `FreshnessBadge`). Every screen renders loading / empty / error;
the empty state is the common case and is informative (e.g. "no signals yet —
gold_trading_signals is empty").

## Stubs / explicit degradations (and why)

- **Delta reads** return a well-formed empty envelope with
  `freshness.state="unavailable"` when pyspark is absent (local) or the Spark
  session cannot start, and `"empty"` when a table has 0 rows on Databricks. No
  placeholder data is fabricated. `read_delta()` (`api/deps.py`) maps these
  cases; routes never crash.
- **Agent chat** is a deterministic keyword dispatch over the existing
  `agent.tools_retrieval` / `agent.tools_write` contracts (visible tool calls +
  evidence). It is not LLM-orchestrated: the inherited
  `api/services/langgraph_engine.py` requires an API key and is left read-only.
- **SEC Filing Explorer** is wired to `POST /api/agent/chat` (search intent) —
  the §10.2 route table has no `/api/sec` route, so no extra route was added.
- **Reject** uses `POST /api/orders/{id}/cancel` (the table has no reject
  route). Risk-check results are shown after approval (the approval response
  carries `risk`); there is no dry-run endpoint because none is in the table.
- **Analytics** returns four empty envelopes (`analytics_*` are 0 rows).
- **Execution bridge** remains an interface (`execution/bridge.py`) — no live
  IBKR connectivity, per non-goals.

## Checks run

```
$ python3 -c "import api.main"        # via PYTHONPATH=. python3 /tmp/_verify.py
IMPORT_OK
POST /api/agent/chat
GET /api/analytics
GET /api/health
GET /api/market/{symbol}
POST /api/orders/intents
POST /api/orders/{order_id}/approve
POST /api/orders/{order_id}/cancel
GET /api/portfolio
GET /api/signals
GET /api/watchlists
```

```
$ cd frontend && npm install && npm run build
node: v22.23.3
npm: 10.9.9
added 134 packages, and audited 135 packages in 12s
> qp1-app-frontend@0.1.0 build
> tsc && vite build
vite v5.4.21 building for production...
✓ 48 modules transformed.
dist/index.html                   0.41 kB │ gzip:  0.29 kB
dist/assets/index-BgWaTU5u.css   14.69 kB │ gzip:  3.42 kB
dist/assets/index-Bd5o1L0e.js   166.67 kB │ gzip: 52.26 kB
✓ built in 1.62s
```

Local smoke test (FastAPI TestClient) returned HTTP 200 for every read route
with explicit `freshness` envelopes; the agent chat correctly resolved
"latest signal for NVDA" → symbol `NVDA` (allow-list-aware extraction in
`api/routes/agent_chat.py`).

## Acceptance criteria

1. `import api.main` succeeds — see above (IMPORT_OK).
2. Every route above exists — see OpenAPI route list above.
3. `npm install && npm run build` succeeds — see output above.
4. No secret/token/connection string committed — all credentials read from env
   (`api/deps.py`, `db/lakebase.py`); `app.yaml` carries only CATALOG/SCHEMA.
5. Forbidden paths — `git diff --name-only main..HEAD` shows only
   `api/`, `frontend/`, `app.yaml`, `docs/`, `requirements-app.txt`, and the
   protocol files; nothing under `agent/`, `db/`, `ml/`, `silver/`, `gold/`,
   `api/services/`, `api/models/`, `tests/ml/`, `conftest.py`, `pytest.ini`,
   `requirements.txt`.
6. Committed to `slice/app-scaffold`; not pushed; `main` untouched.

## Gate

Per PROTOCOL, this is a builder verdict and is **not** the gate. Independent
validation by Codex and Claude is required. I have not opened a PR.
