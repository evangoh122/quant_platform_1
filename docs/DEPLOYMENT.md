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

`app.yaml` starts `uvicorn api.main:app` bound to `0.0.0.0:8000`.

## 2. Pre-deploy build

The frontend must be built **before** the app is deployed so the backend can
serve it (the Databricks App runtime does not run `vite build`).

```bash
# From the repo root — installs deps + builds in one step:
./scripts/build_frontend.sh
# produces frontend/dist/
```

The script runs `npm ci && npm run build` inside `frontend/` and exits
non-zero on any failure.  `frontend/dist/` is gitignored but included in
the bundle via `sync.include` in `databricks.yml`.

## 3. Create the app

1. Workspace → **Compute → Apps → Create app** (or `databricks apps init` /
   `databricks apps deploy` for a CLI/DABs workflow — see §7).
2. Point the source at this repository directory.
3. Set the `app.yaml` command to `uvicorn api.main:app --host 0.0.0.0 --port 8000`.
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
| `gold_sec_kg_nodes` | agent `query_sec_facts` tool |
| `gold_sec_kg_edges` | agent `query_sec_facts` tool |

```sql
GRANT SELECT ON TABLE bootcamp_students.evangoh_capstone.gold_trading_signals
  TO `<app-service-principal>`;
GRANT SELECT ON TABLE bootcamp_students.evangoh_capstone.gold_ohlcv_features
  TO `<app-service-principal>`;
GRANT SELECT ON TABLE bootcamp_students.evangoh_capstone.gold_options_features
  TO `<app-service-principal>`;
GRANT SELECT ON TABLE bootcamp_students.evangoh_capstone.silver_sec_sections
  TO `<app-service-principal>`;
GRANT SELECT ON TABLE bootcamp_students.evangoh_capstone.gold_sec_kg_nodes
  TO `<app-service-principal>`;
GRANT SELECT ON TABLE bootcamp_students.evangoh_capstone.gold_sec_kg_edges
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

### Lakebase resource declaration (DABs)

The Lakebase database is declared in `resources/app.yml` so Databricks Apps
provisioning connects the app to the correct instance:

```yaml
resources:
  - name: lakebase
    database:
      instance: evangoh-capstone-lakebase
      permission: CAN_CONNECT_AND_CREATE
```

### Required Postgres grants

The app's database role needs these grants on the `public` schema. Run these
as the Lakebase database owner:

```sql
-- Schema access
GRANT USAGE ON SCHEMA public TO "<app-database-role>";

-- User identity (read own role, upsert new users)
GRANT SELECT, INSERT ON TABLE public.users TO "<app-database-role>";

-- Operational tables used by portfolio/watchlist/orders
GRANT SELECT, INSERT, UPDATE ON TABLE public.watchlists TO "<app-database-role>";
GRANT SELECT, INSERT, UPDATE ON TABLE public.orders TO "<app-database-role>";
GRANT SELECT, INSERT, UPDATE ON TABLE public.positions TO "<app-database-role>";
GRANT SELECT, INSERT ON TABLE public.approvals TO "<app-database-role>";
GRANT SELECT, INSERT ON TABLE public.executions TO "<app-database-role>";
GRANT SELECT, INSERT ON TABLE public.agent_actions TO "<app-database-role>";
GRANT SELECT, INSERT ON TABLE public.research_notes TO "<app-database-role>";
GRANT SELECT, INSERT ON TABLE public.accounts TO "<app-database-role>";
```

Replace `<app-database-role>` with the Lakebase database role for the app's
service principal. Do **not** grant `CREATE` on the schema or `ALL` on any table.

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

Deploying the Databricks App via CLI follows this sequence:

```bash
# 1. Build the frontend (produces frontend/dist/)
./scripts/build_frontend.sh

# 2. Validate the bundle
databricks bundle validate --profile <PROFILE>

# 3. Deploy the bundle (syncs code + resources to the workspace)
databricks bundle deploy --profile <PROFILE>

# 4. Start the app
databricks apps start --profile <PROFILE>

# 5. Smoke-test the deployed app
python scripts/smoke_app.py <APP_URL>
```

The `sync.include` directive in `databricks.yml` ensures `frontend/dist/`
is uploaded even though it is gitignored. If `frontend/dist/` does not
exist at deploy time the API still starts, but `GET /` returns a hint
instead of the SPA.

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

## 10. Render deployment — proxy trust and rate limiting

When deploying on Render, the following configuration applies:

### Fail-closed startup guard

On Render (the `RENDER` environment variable is set), the application
**refuses to start** unless `PUBLIC_DEMO=1` is also set. This prevents the
insecure default where an absent `PUBLIC_DEMO` silently enables the full
write surface. Set `PUBLIC_DEMO=1` explicitly in the Render service
environment.

### Rate limiter — IP extraction (`CLIENT_IP_SOURCE`)

The source of the client IP for rate limiting is controlled by the
`CLIENT_IP_SOURCE` environment variable:

| Value | Default on | Behaviour |
|-------|-----------|-----------|
| `xff_leftmost` | **Render** | Leftmost `X-Forwarded-For` entry if valid; otherwise `request.client.host`. **Never reads** `CF-Connecting-IP` or `True-Client-IP`. |
| `cf_connecting_ip` | — | `CF-Connecting-IP` only (valid IP); otherwise `request.client.host`. Opt-in for verified Cloudflare setups. |
| `peer` | **non-Render** | `request.client.host` only; all headers ignored. |

An unrecognised value raises `PublicDemoConfigurationError` at startup.

**Why `xff_leftmost` is the default on Render:**

Render's documentation states: *"we set the first IP in the list to the real
client IP"* ([source](https://render.com/docs/forwarding-and-proxying)).
The `CF-Connecting-IP` and `True-Client-IP` headers are **not** rewritten
by Render — a client can set them to arbitrary values. DeepSeek's check6
proved that trusting `CF-Connecting-IP` first is spoofable: rotating the
header 200x gives 200/200 accepted, then a real client gets 429.

Outside Render (no `RENDER` env var), the default is `peer` and all headers
are ignored regardless of `CLIENT_IP_SOURCE`.

We avoid using `--forwarded-allow-ips='*'` because that would make
`request.client.host` read from the (spoofable) `X-Forwarded-For` header.

The per-IP limit defaults to 60 req/min; an aggregate token bucket of 600
tokens refills at 10 tokens/sec, so bursts cause brief 429s that
self-recover within seconds rather than a hard minute-long outage. Both
are configurable via `RATE_LIMIT_READS` and `RATE_LIMIT_GLOBAL`. The LRU
cap on distinct IP keys defaults to 10,000 (configurable via
`RATE_LIMIT_LRU_MAX`).

### Uvicorn startup command

```bash
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

Do **not** pass `--forwarded-allow-ips='*'`. Render's proxy is not trusted
at the uvicorn level; the application reads headers directly for
rate-limiting purposes only.

### Post-deploy verification

After deploying, run these checks before going public:

```bash
# (a) Confirm which IP the limiter keys on.
# Enable diagnostic logging, send X-Forwarded-For, check the log (redacted key).
# Set RATE_LIMIT_DEBUG=1 in your Render service env, then:
curl -H "X-Forwarded-For: 1.2.3.4" https://YOUR_APP.onrender.com/api/health
# The log should show: rate_limit_debug client_ip_source=xff_leftmost key=1.2.x.x
# If the key is "1.2" something is wrong (the redacted format must be "1.2.x.x").
# Turn RATE_LIMIT_DEBUG off after verification.

# (b) Confirm per-IP limiting with spoofed headers.
# From one machine, send 70 requests with rotating spoofed XFF,
# CF-Connecting-IP, and True-Client-IP headers.
# Request 61 should get 429 (one bucket, spoofed headers ignored).
for i in $(seq 1 70); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "X-Forwarded-For: 10.0.$(( RANDOM % 256 )).1" \
    -H "CF-Connecting-IP: $(( RANDOM % 256 )).$(( RANDOM % 256 )).$(( RANDOM % 256 )).$(( RANDOM % 256 ))" \
    -H "True-Client-IP: $(( RANDOM % 256 )).$(( RANDOM % 256 )).$(( RANDOM % 256 )).$(( RANDOM % 256 ))" \
    https://YOUR_APP.onrender.com/api/health
done | sort | uniq -c

# (c) If (b) fails (no 429s), switch CLIENT_IP_SOURCE.
```

If verification shows that spoofed headers bypass the limiter, set
`CLIENT_IP_SOURCE=peer` as an immediate mitigation and investigate the
proxy configuration.

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

## 11. SEC Knowledge Graph build (manual job)

The SEC knowledge graph (`gold_sec_kg_nodes`, `gold_sec_kg_edges`) is built by
an **unscheduled** job named `sec_knowledge_graph_build`. It must be triggered
manually or via CI — it is not part of the scheduled `silver_gold_refresh` chain.

### Running the build

```bash
# Offline (JSONL output)
python scripts/build_sec_knowledge_graph.py \
  --entities evals/data/sec_entities.jsonl \
  --corpus evals/data/sec_corpus.jsonl \
  --output-dir /tmp/sec-kg-output \
  --format jsonl

# Databricks (Delta tables)
databricks jobs run-now --job-name sec_knowledge_graph_build \
  --profile <PROFILE>
```

### Grants for the build job

The build service principal needs `MODIFY` on the target tables:

```sql
GRANT MODIFY ON TABLE bootcamp_students.evangoh_capstone.gold_sec_kg_nodes
  TO `<build-service-principal>`;
GRANT MODIFY ON TABLE bootcamp_students.evangoh_capstone.gold_sec_kg_edges
  TO `<build-service-principal>`;
```

### Compaction / OPTIMIZE

After significant data growth, run `OPTIMIZE` on the Delta tables:

```sql
OPTIMIZE bootcamp_students.evangoh_capstone.gold_sec_kg_nodes
  ZORDER BY (node_type);
OPTIMIZE bootcamp_students.evangoh_capstone.gold_sec_kg_edges
  ZORDER BY (edge_type, valid_from);
```

Do not schedule `OPTIMIZE` in this task — document it for operator use.

### concept_norm migration (round 12+)

The `concept_norm` column on `gold_sec_kg_nodes` enables structured concept
searches (NFKC-normalised, lower-cased).  Pre-round-12 tables lack this column.

**Migration:** The build job automatically runs `ALTER TABLE ... ADD COLUMNS
(concept_norm STRING)` if the column is missing (idempotent, re-runnable).
A full rebuild then populates `concept_norm` for all rows via the MERGE
`whenMatchedUpdateAll` path.

**NULL handling:** If concept searches are attempted before a rebuild has run,
the query path detects NULL `concept_norm` rows and raises a clear
`RuntimeError` instead of silently omitting legacy rows.  This is a deliberate
fail-fast: concept searches require a populated `concept_norm` column.

**Operator action:** After upgrading to round 12+, trigger a full SEC knowledge
graph build to backfill `concept_norm`:

```bash
databricks jobs run-now --job-name sec_knowledge_graph_build --profile <PROFILE>
```

## 12. Render public demo

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
