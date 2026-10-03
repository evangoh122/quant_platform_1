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
  `x-forwarded-email`. `api/deps.py` trusts **only** that header (overridable via
  `AUTH_USER_HEADER`); other identity headers such as `x-forwarded-user` and
  `x-databricks-user` are ignored. A missing header returns `401`, except when
  `APP_ENV=dev` is set explicitly, and the dev fallback principal is rejected by
  every write route. This relies on the proxy overwriting `x-forwarded-email`;
  if the app is reachable without the proxy, the header can be forged.
- One role model, enforced server-side by `require_role` and again in
  `agent/tools_write.record_approval`:

  | Role | Can |
  | :-- | :-- |
  | `viewer` | read only — the role every newly seen identity receives |
  | `trader` | write (watchlists, order intents, cancels) and approve **their own** orders |

  `trader` is granted only out-of-band with `python scripts/grant_approver.py <user_id>`
  (see below). A role-store failure returns `503`, never a role.
- The browser never receives broker credentials and never connects directly to
  Lakebase, Delta, SEC, the market-data provider, or IBKR. All outbound calls
  are server-side.
- CORS is disabled by default (same-origin). Enable only for local dev via
  `CORS_ORIGINS=http://localhost:5173`.

## Lakebase agent tools — approver authority and migrations

### Approver authority (out-of-band grant only)

Approval of a paper order is recorded by `agent/tools_write.record_approval`,
which accepts only an `ApprovalContext` whose `approver_id`:

1. is an actual `ApprovalContext` instance;
2. resolves to an existing `users` row whose `role` is `'trader'`;
3. is the **owner** of the order (a single-user paper-trading tool: "explicit
   human approval" means a user confirming their own order).

`role = 'trader'` is **never** granted automatically:

- `agent/tools_write._ensure_user` provisions previously-unseen identities with
  the non-approving `'viewer'` role.
- No module under `agent/` may insert or update `users.role`.

The only path to `'trader'` is the out-of-band admin CLI:

```bash
python scripts/grant_approver.py <user_id>
```

Run it as a human operator for each principal you have explicitly vetted. The
remediation migration `db/migrations/003_revoke_auto_provisioned_approvers.sql`
downgrades every pre-existing `'trader'` row to `'viewer'`; re-grant vetted
principals after applying it.

### Applying migrations

```bash
python -m db.migrate
```

Forward-only, ordered by filename, re-runnable. Applied versions are recorded in
`schema_migrations`.

## 10. Render public demo

This section describes the **Render public demo** — a single-service snapshot
demo that is separate from the Databricks deployment described in §1–§9 above.
It is defined in §7 of `docs/RENDER_DEPLOY_PLAN.md` and governed by the
Render lane build request (R1 + R8).

### Purpose

The Render demo is a publicly accessible, read-only showcase. It serves
pre-reviewed snapshot data through `demo_data/` and contains **no credentials**,
**no Lakebase connection**, and **no live Databricks access**. It is deployed
independently via manual deploy and requires Lane B/C safety gates before any
public URL is shared.

### Environment

The service runs with these environment variables only:

| Variable | Value | Purpose |
| :--- | :--- | :--- |
| `PUBLIC_DEMO` | `1` | Enables demo mode; disables all write routes and identity headers |
| `APP_ENV` | `demo` | Selects demo data sources |

**No secrets are configured.** The following variable families must never
appear in the Render service configuration:

- `LAKEBASE_*` — Lakebase connection and OAuth tokens
- `DATABRICKS_*` — Databricks workspace, SQL warehouse, and service principal credentials
- Broker/API tokens: `POLYGON_API_KEY`, `IBKR_*`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- Credential-like frontend variables: any `VITE_*` value that contains a token, key, or secret

Variable names in documentation are allowed; actual secret values are not.

### Build

```bash
pip install -r requirements-render.txt && cd frontend && npm ci && npm run build
```

This installs only the four minimal runtime dependencies (fastapi, uvicorn,
pydantic, loguru) and builds the React frontend into `frontend/dist/`. Node
must be available in the Python build environment.

### Start

```bash
uvicorn api.main:app --host 0.0.0.0 --port $PORT --proxy-headers
```

The `$PORT` variable is injected by Render. The app serves both the API
(`/api/*`) and the built frontend (`frontend/dist/`) from a single process.

### Smoke tests

After deploy, verify from the Render service URL:

```bash
# 1. Health check
curl -s $RENDER_URL/api/health

# 2. Frontend served same-origin
curl -s -o /dev/null -w '%{http_code}\n' $RENDER_URL/

# 3. SPA deep link (must return index.html, not 404)
curl -s -o /dev/null -w '%{http_code}\n' $RENDER_URL/results/walk-forward
```

Expected: `/api/health` returns 200; `/` and the deep link both return 200
with the SPA shell (`index.html`). Deep links must not return 404 — the
FastAPI static file handler falls back to `index.html` for any path not
matching `/api/*`.

### SPA deep-link behavior

All non-API routes serve `frontend/dist/index.html` so that client-side
routing works for paths like `/results/walk-forward`, `/signals`, `/market/NVDA`,
and `/agent`. The backend does not swallow `/api/*` routes — those are handled
by FastAPI routers before the static file fallback.

### Rollback / manual deploy

The service uses `autoDeploy: false`. To deploy:

1. Push the latest code to the `slice/render-lane-a` branch.
2. In the Render dashboard, select the `qp1-showcase` service and click
   **Manual Deploy > Deploy latest commit**.
3. Wait for the build to complete and the health check to pass.

To rollback: select a previous deploy in the Render dashboard and click
**Redeploy**. No automatic rollback is configured.

### Safety gates

This service must not be made public until the following Lane B and Lane C
gates are complete:

- **Lane B** (R2, R3, R4, R7; PR #21): demo-mode access control, write-surface
  removal, startup secret checks, and abuse controls (rate limits, headers).
- **Lane C** (R5, R6): snapshot reader validation and snapshot export tooling.

Without these gates, the service would expose write endpoints and trust
spoofed identity headers.
