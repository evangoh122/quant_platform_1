# Deployment — Databricks App

This document covers packaging the FastAPI + React application as a Databricks
App. **Nothing here is executed by the scaffold slice** — these are the manual
steps an operator runs to ship the app.

## 1. What gets deployed

A single Databricks App serving both layers from one process (required — the
Databricks Apps reverse proxy expects **one** process bound to
`DATABRICKS_APP_PORT`):

- **Backend** — FastAPI under `api/` (`api.main:app`), all routes under `/api`.
- **Frontend** — the built React SPA in `frontend/dist/`, served as static files
  by the backend when `frontend/dist/` exists.

`app.yaml` starts `uvicorn api.main:app` bound to `0.0.0.0:${DATABRICKS_APP_PORT:-8000}`.

## 2. Pre-deploy build

The frontend must be built **before** the app is deployed so the backend can
serve it (the Databricks App runtime does not run `vite build`).

```bash
cd frontend && npm install && npm run build
# produces frontend/dist/
```

## 3. Create the app

1. Workspace → **Compute → Apps → Create app** (or `databricks apps init` /
   `databricks apps deploy` for a CLI/DABs workflow — see §7).
2. Point the source at this repository directory.
3. Set the `app.yaml` command to `uvicorn api.main:app --host 0.0.0.0 --port ${DATABRICKS_APP_PORT:-8000}`.
4. Deploy.

## 4. Required Unity Catalog permissions

The app's service principal must be able to read the serving tables it exposes.
Grant the **least privilege** that covers the API surface:

| Table | Access needed by |
| :-- | :-- |
| `gold_trading_signals` | `GET /api/signals` |
| `gold_ohlcv_features` | `GET /api/market/{symbol}` |
| `gold_options_features` | `GET /api/market/{symbol}` |
| `silver_sec_sections` | agent `search_sec_filings` tool |

```sql
GRANT SELECT ON TABLE bootcamp_students.evangoh_capstone.gold_trading_signals
  TO `<app-service-principal>`;
GRANT SELECT ON TABLE bootcamp_students.evangoh_capstone.gold_ohlcv_features
  TO `<app-service-principal>`;
GRANT SELECT ON TABLE bootcamp_students.evangoh_capstone.gold_options_features
  TO `<app-service-principal>`;
GRANT SELECT ON TABLE bootcamp_students.evangoh_capstone.silver_sec_sections
  TO `<app-service-principal>`;
```

The app does **not** need `CREATE`/`MODIFY` on any UC table — it is read-only on
Delta. All writes go to Lakebase (Postgres), see §5.

## 5. Lakebase connection — least privilege

`db/lakebase.py` mints a short-lived OAuth token **on demand** via the
`databricks` CLI and keeps it only in memory. It never reads a hard-coded
password. Configure connection parameters as environment variables:

| Env var | Purpose |
| :-- | :-- |
| `LAKEBASE_INSTANCE` | Lakebase instance name (token mint) |
| `LAKEBASE_HOST` / `LAKEBASE_PORT` | Postgres endpoint |
| `LAKEBASE_DBNAME` | Database name |
| `LAKEBASE_USER` | OAuth user email |
| `LAKEBASE_SCHEMA` | Schema (default `public`) |
| `LAKEBASE_SSLMODE` | `require` |
| `LAKEBASE_POOL_MIN_SIZE` / `LAKEBASE_POOL_MAX_SIZE` | Pool sizing |

Least-privilege guidance:

- Use the **application's own service principal / app identity** for the Lakebase
  token, scoped to the `public` schema it operates on — not a workspace-admin
  identity.
- Grant only `SELECT/INSERT/UPDATE/DELETE` on the operational tables the app
  writes (`users`, `watchlists`, `orders`, `approvals`, `executions`,
  `positions`, `agent_actions`, `research_notes`, `accounts`), and nothing else.
- Do **not** grant `CREATE DATABASE`/`DROP` or any admin role.

## 6. Secrets — Databricks secrets only

No secret, token, or connection string is ever committed. Every credential is
resolved from an environment variable at runtime, and sensitive values are
stored in a **Databricks secret scope** and injected into the app env.

```bash
databricks secrets create-scope --scope quant-app
databricks secrets put --scope quant-app --key lakebase-user --string "you@example.com"
# ... then reference via the app's env config (Databricks Apps injects secrets
#     referenced by the app config into the container env).
```

The app reads these through the standard env-var names in `.env.example`
(reference only — do not commit values). API keys that power the research agent
(if an LLM is added later) must follow the same path: `DEEPSEEK_API_KEY`,
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `POLYGON_API_KEY`, etc.

**Never** put a `databricks` personal access token, OAuth client secret, or
Lakebase password in `app.yaml`, `requirements-*.txt`, or any committed file.

## 7. CLI / DABs deployment (alternative to the UI)

```bash
databricks apps validate --profile <PROFILE>
databricks apps deploy --profile <PROFILE>
databricks apps get <app-name> --profile <PROFILE>   # confirm status RUNNING + url
```

## 8. Smoke tests (rubric §11)

After deploy, verify from the app URL (`https://<app-name>.<region>.databricksapps.com`):

```bash
# 1. Health — expects status ok|degraded with dependency list
curl -s $APP_URL/api/health

# 2. Signals — well-formed empty envelope (empty table today)
curl -s $APP_URL/api/signals

# 3. Market — well-formed empty envelope for a symbol
curl -s $APP_URL/api/market/NVDA

# 4. Portfolio — positions + orders envelopes
curl -s $APP_URL/api/portfolio

# 5. Watchlist read
curl -s $APP_URL/api/watchlists

# 6. Analytics — four empty envelopes
curl -s $APP_URL/api/analytics

# 7. Agent chat — deterministic tool-call scaffold (no LLM key required)
curl -s -X POST $APP_URL/api/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"latest signal for NVDA"}'

# 8. Frontend served same-origin
curl -s -o /dev/null -w '%{http_code}\n' $APP_URL/
```

Expected: every `/api` call returns HTTP 200 with a JSON envelope carrying an
explicit `freshness` field (`empty` or `unavailable` while backing tables are
unpopulated). Writes (`POST /api/watchlists`, `/api/orders/intents`,
`/api/orders/{id}/approve`, `/api/orders/{id}/cancel`) return 201/200 on success
or a structured 503 when Lakebase is unreachable — never a 500 crash.

## 9. Authentication & authorization

- The Databricks App reverse proxy injects the authenticated user's email into
  `x-forwarded-email` (with `x-databricks-user` as fallback). `api/deps.py`
  maps it to a Lakebase `user_id` and enforces roles **server-side**
  (`require_role`), so no client can escalate or impersonate.
- The browser never receives broker credentials and never connects directly to
  Lakebase, Delta, SEC, the market-data provider, or IBKR. All outbound calls
  are server-side.
- CORS is disabled by default (same-origin). Enable only for local dev via
  `CORS_ORIGINS=http://localhost:5173`.
