# BUILD-REQUEST: app-scaffold

**Branch:** `slice/app-scaffold` (off `main`)
**Worktree:** `/home/jianj/code/qp1-app`
**Rubric:** §G / §10 Frontend (React + TypeScript + Tailwind), §10.2
frontend-to-backend contract, §11 Databricks App deployment.

## Goal

Turn this repo from a collection of Python packages into an **application**.
The structural problem is not that the existing packages sit in the wrong place
— it is that **the application itself does not exist**: there is no backend
entrypoint, `api/routes/` is empty, and there is no frontend at all.

## Current layout (after two completed restructure rounds)

```
agent/  api/  config/  db/  docs/  etl/  evals/  execution/  gold/
ml/  notebooks/  ontology/  pipelines/  silver/  strategies/  tests/
app.yaml  conftest.py  pytest.ini  requirements.txt  README.md
```

`api/` already holds `api/services/` (43 modules), `api/models/`, `api/config.py`
and an **empty** `api/routes/`. Those services came from a RAG application and
are reusable — **import them, do not edit them.**

## Scope

### 1. Backend — FastAPI application under `api/`

Create:
- `api/main.py` — the FastAPI app; mounts routers, health endpoint, CORS off by
  default (same-origin per the rubric), and serves the built frontend as static
  files in production.
- `api/deps.py` — dependency providers: Lakebase connection, Spark/Delta reader,
  the authenticated app user, and role checks. The rubric requires the backend
  to map the authenticated Databricks App user to a Lakebase `user_id` and
  enforce authorization **server-side**.
- `api/routes/` — one module per resource, exactly these paths (rubric §10.2):

| Route | Method | Reads/writes |
| :-- | :-- | :-- |
| `/api/health` | GET | dependency + freshness status |
| `/api/signals` | GET | `gold_trading_signals` |
| `/api/market/{symbol}` | GET | `gold_ohlcv_features`, `gold_options_features` |
| `/api/agent/chat` | POST | agent runtime |
| `/api/watchlists` | GET, POST | Lakebase `watchlists` |
| `/api/orders/intents` | POST | Lakebase `orders` (PENDING_APPROVAL) |
| `/api/orders/{id}/approve` | POST | risk service + execution bridge |
| `/api/orders/{id}/cancel` | POST | execution bridge |
| `/api/portfolio` | GET | Lakebase `positions`, `orders` |
| `/api/analytics` | GET | analytics tables (may return empty for now) |

**Critical constraints:**
- The browser must **never** receive broker credentials or connect directly to
  Lakebase, Delta, SEC, the market-data provider or IBKR. All outbound calls are
  server-side.
- `agent/` and `db/` are owned by another live lane — **import them, never edit
  them.** The order routes must call the existing
  `agent.tools_write.approve_and_place_paper_order(order_id)` rather than
  reimplementing risk logic. Note its public signature deliberately takes only
  the order id.
- Where a backing table is still empty (all `gold_*` and `analytics_*` are
  currently 0 rows), return a well-formed empty response **with an explicit
  freshness/empty indicator**. Do not fabricate placeholder data, and do not
  crash.

### 2. Frontend — `frontend/`, React + TypeScript + Tailwind

Scaffold with Vite. Create the eight rubric screens as real components wired to
the API client (they may render empty states where data is absent):

1. Market Dashboard — OHLCV, options activity, model score, freshness indicator
2. Signal Explorer — ranked signals, probability, feature contributions
3. Options Analytics — chain metrics, IV/skew, unusual volume
4. SEC Filing Explorer — section search, extracted events, source links
5. AI Research Agent — chat, visible tool calls/evidence, save note/watchlist
6. IBKR Paper Portfolio — positions, open orders, fills, P&L
7. Order Approval Drawer — exact order, signal age, risk-check results, approve/reject
8. Analytics / System Health — model performance, agent activity, p50/p95 latency, stream freshness

Requirements:
- One typed API client (`frontend/src/api/`) with types mirroring the backend
  response models. No `any`.
- Tailwind configured; a small shared component set (card, table, stat tile,
  empty state, error state). Do not pull in a heavy component library.
- Every screen must handle three states explicitly: loading, empty, error. Given
  most tables are empty today, **the empty state is the common case** — make it
  informative ("no signals yet — gold_trading_signals is empty"), not a blank div.
- `npm run build` must succeed. Paste the output.

### 3. Databricks App packaging

- Update `app.yaml` (currently 13 lines) to run the FastAPI app correctly as a
  Databricks App, serving the built frontend.
- Document the deploy steps in `docs/DEPLOYMENT.md`: app creation, required UC
  permissions, Lakebase connection with least-privilege credentials, secrets via
  Databricks secrets (never hard-coded), and the smoke tests per rubric §11.
- **Do not deploy anything.** Packaging and documentation only.

### 4. Document the application layout

Update `docs/STRUCTURE.md` to describe the resulting application structure, one
line per top-level directory, making clear which are app runtime (`api/`,
`frontend/`, `agent/`, `execution/`), which are data pipeline (`etl/`, `silver/`,
`gold/`, `pipelines/`), and which are research (`ml/`, `strategies/`, `evals/`,
`notebooks/`).

## Non-goals — do not build

- No ML models (a concurrent lane owns `ml/`).
- No silver/gold transforms (concurrent lane owns `silver/`, `gold/`).
- No real IBKR connectivity; the bridge stays an interface.
- Do not move or rename existing packages. The layout above is the target; the
  gap is the missing app, not misplaced folders.

## Paths you must NOT touch

`agent/`, `db/` (live lane — import only), `ml/`, `tests/ml/` (live lane),
`silver/`, `gold/` (live lane), `api/services/`, `api/models/` (read-only
inherited code), `conftest.py`, `pytest.ini`, `requirements.txt`, `.agents/`.

Add backend deps to a **new** `requirements-app.txt` rather than editing
`requirements.txt`, which another lane owns.

## Acceptance criteria

1. `python3 -c "import api.main"` succeeds. Paste it.
2. Every route above exists and returns a valid response (or a well-formed
   empty/unavailable response) — paste a route list, e.g. from the OpenAPI schema.
3. `cd frontend && npm install && npm run build` succeeds. Paste the output.
4. No secret, token or connection string committed. Config via env var only.
5. No forbidden path in `git diff --name-only main..HEAD`. Check and paste it.
6. **Commit to `slice/app-scaffold`.** Never push, never touch `main`.

## When finished

`.agents/deepseek/VERDICT-app-scaffold.md` per `.agents/PROTOCOL.md`, listing
the routes implemented, the screens created, and anything stubbed and why.
