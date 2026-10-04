===VERDICT START===
# VERDICT: render-lane-b — DeepSeek (security lane, independent check)

**Status:** CHANGES_REQUESTED
**Round:** 1 (security check per `CHECK-render-lane-b.md`)
**Branch:** `slice/render-lane-b` (HEAD `36db276`; lane code `6365661`, round-2 fixes `888f757`)

Checker verdict: I read the diff and attacked the demo gate; I did **not** modify the
worktree. All scratch work lived under `/tmp/qp1-attack/`.

## Summary

The core boundary works: when `PUBLIC_DEMO` is a normalized truthy value, the write
surface is gone (routes unregistered, openapi hidden, all 7 tools guarded before any
side effect), spoofed identity headers are ignored, and reads are rate-limited. I
could not reach a write or read the exported secret via the SPA catch-all. Two real
defects remain and must be fixed before this ships as a public site.

## Blocking findings

1. **[api/routes/health.py:22-35] `/api/health` imports `db.lakebase` and performs a
   live Lakebase probe in demo mode.** `create_app()` registers `health.router` in both
   modes, and the handler does `from db.lakebase import get_lakebase` then
   `get_lakebase().fetchone("SELECT 1")`. This:
   - violates the "demo never touches Lakebase" design (R8 note 8) and the smoke-test
     claim that `db.lakebase` is never imported — I confirmed `db.lakebase` lands in
     `sys.modules` after `GET /api/health` in demo (`agent.tools_write` correctly does not);
   - shells out to the `databricks` CLI (`mint_token_via_cli`) and opens a real TCP
     connection to the hardcoded endpoint
     `ep-steep-truth-d1ex36nr.database.us-west-2.cloud.databricks.com` with user
     `evangohsg@gmail.com` (`db/lakebase.py:28-35`) on every poll. Render's
     `healthCheckPath` **is** `/api/health`, so this runs continuously in production;
   - runs synchronous psycopg inside the async handler, blocking the event loop. In
     this environment it returned **504** (10 s middleware timeout) instead of the
     expected `200 degraded`. On Render (no `databricks` CLI) it degrades faster but
     still spawns a subprocess per poll.
   The test `test_no_lakebase_import_in_demo` only probes `/api/analytics`, so it never
   catches this. Fix: short-circuit the Lakebase probe in demo (`health.py` should
   report the dependency as skipped/unavailable without importing or calling
   `db.lakebase`).

2. **[api/main.py:80-135 + api/demo.py:18-25] Fail-open default.** `is_public_demo()`
   is false when `PUBLIC_DEMO` is unset, empty, or any value outside `{1,true,yes,on}`
   (verified: `""`, `"0"`, `"1.0"`, `"t"` → demo OFF). With demo off, `create_app()`
   registers the full write surface and the spoofable `x-forwarded-email` identity path
   (confirmed via non-demo `openapi.json`: `POST /api/orders/intents`,
   `/api/orders/{id}/approve`, `/cancel`, `POST /api/watchlists`,
   `POST /api/agent/chat` all present; spoofed email reaches `_ensure_user`/DB lookup).
   `validate_public_demo_environment()` runs **only** when demo is already on, so it
   cannot guard the "demo accidentally off" state. `render.yaml` does not exist in this
   repo (it is the R8 deliverable), so the *default* state of the deployed code is the
   insecure one. Recommend a fail-closed inverse check (e.g. refuse to start with the
   write routers when `APP_ENV`/`PUBLIC_DEMO` is absent in a Render/production context),
   or at minimum gate `render.yaml` as a hard pre-merge requirement.

## Non-blocking notes

- **[api/main.py:149-181] Security headers are missing on 405/413/429.** The middleware
  returns `JSONResponse` for 405 (method), 413 (oversize), and 429 (rate limit) *before*
  the header block, so those responses carry none of `X-Content-Type-Options`,
  `Referrer-Policy`, `X-Frame-Options`, `Content-Security-Policy`, or
  `Cache-Control: no-store` (verified by raw-ASGI: only 200 and 504 get them; 429 gets
  only `Retry-After`). This contradicts the spec's "preserve security headers on
  4xx/5xx/429/504". Move header application before the early returns or into a shared
  helper.

- **[api/demo.py:46-56] Secret-check families are narrower than the threat list.**
  Confirmed slipping through: `PGPASSWORD`/`PG*`, generic `*_PASSWORD` (`DB_PASSWORD`,
  `POSTGRES_PASSWORD`), `*_KEY` (`SECRET_KEY`, `JWT_KEY`, `POLYGON_KEY`),
  `DATABASE_URL`, and `IBKR_*` variants beyond the explicit list (`IBKR_BASE_URL`,
  `IBKR_ACCOUNT_ID`, `IBKR_SESSION`). `_API_KEY`/`_TOKEN`/`_SECRET` suffixes and
  `LAKEBASE_`/`DATABRICKS_` prefixes are correctly caught. The app (config.py) only reads
  `_API_KEY`-suffixed vars today, so current exposure is low, but recommend broadening to
  `*_PASSWORD`, `*_KEY`, `PG*`, `DATABASE_URL`, and the `IBKR_` prefix.

- **[api/main.py:174-181] 413 relies on Content-Length only.** Streamed/chunked bodies
  (no `Content-Length`) are never size-bounded, so the spec's "from streamed bytes"
  requirement is unmet. In demo, non-GET/HEAD/OPTIONS are 405'd before any body is read,
  so the practical impact is limited to GET/OPTIONS with chunked bodies (routers do not
  consume those), but the stated requirement is not implemented.

- **[api/main.py:164] Rate limiter keyed on `request.client.host` behind Render's
  `--proxy-headers`.** The code correctly avoids reading `X-Forwarded-For` directly. But
  the planned `startCommand` uses `--proxy-headers`, and uvicorn (0.54.0) only rewrites
  `client` from forwarded headers when the peer is in `forwarded_allow_ips` (default
  `127.0.0.1`). Two outcomes, both wrong: (a) default — Render's proxy isn't trusted, so
  all visitors share one proxy IP → the "per-IP" limit collapses to a single ~60/min
  global bucket (availability/DoS); (b) if `FORWARDED_ALLOW_IPS=*` is set (common to get
  real IPs), `request.client.host` becomes the spoofable X-Forwarded-For → limit evasion
  plus unbounded `_limiter` growth (distinct spoofed IPs accumulate within the current
  window). Recommend documenting the exact Render proxy trust config and/or bounding the
  limiter with an LRU cap on distinct keys.

- **[api/main.py:154] `/api` prefix check is evadable** by `//api/…`, `/%2fapi/…`,
  `/API/…` (verified: `POST //api/orders` returns Starlette's `Method Not Allowed`
  405, not the middleware's demo 405; `GET //api/analytics` is neither rate-limited nor
  `no-store`). No sensitive data is reached (routes only match the canonical path; these
  fall through to the GET-only SPA catch-all), so this is defense-in-depth inconsistency,
  not a write path.

- **[tests/api/test_public_demo_security.py:112-129] Route-enumeration assertions may pass
  vacuously on FastAPI 0.142.** `app.routes` exposes `_IncludedRouter` placeholders with
  `path=None`/`methods=set()`, so the "methods ⊆ {GET,HEAD,OPTIONS}" loop and the
  "prohibited paths absent" set are trivially true. The functional behavior (405 for
  writes, 404/405 for absent paths) is nonetheless correct — verified via TestClient and
  raw ASGI.

## What I could NOT break (verified)

- **Bypass demo mode:** value normalization is correct for the 4 truthy values; the
  guard re-reads the env at call time. `"0"`/`""`/`"1.0"`/`"t"` correctly disable demo.
- **Reach a write:** HEAD/PUT/PATCH/DELETE, `X-HTTP-Method-Override`, trailing slash,
  `//api/orders`, URL-encoded path segments, and the SPA catch-all all return 405/404;
  no write handler is reachable and `agent.tools_write`/broker modules are never imported.
- **SPA path traversal:** `GET /../secret.txt`, `/%2e%2e/%2e%2e/secret.txt`, and
  `/%2e%2e%2f…` all served `index.html` (Starlette normalizes `..`); `FileResponse` never
  returned the out-of-dist sentinel file.
- **Spoofed identity:** fixed anonymous viewer, identical response with/without header.
- **Write-tool guards:** all 7 tools raise `PublicDemoWriteDisabled` before any
  DB/transaction/audit/risk/clock/broker call (mock `assert_not_called` holds).
- **read_delta seam:** demo path never calls live `fn`; missing `api.demo_data` degrades
  cleanly to `unavailable`.
- **No secrets committed:** grep found no literal keys/passwords; the only PII-ish item is
  the hardcoded default Lakebase username/host in `db/lakebase.py` (pre-existing).

## Checks run

```
# Lane acceptance (public-demo)
PUBLIC_DEMO=1 python3 -m pytest -q -p no:cacheprovider tests/api/test_public_demo_security.py tests/lakebase/test_public_demo_write_guard.py
→ 29 passed in 1.01s

# Lane acceptance (non-demo API + lakebase boundary)
python3 -m pytest -q -p no:cacheprovider tests/api tests/lakebase/test_guardrails.py tests/lakebase/test_execution_boundary.py
→ 67 passed in 22.50s

# Full suite excluding lakebase (CHECK command)
python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
→ 501 passed, 67 skipped in 142.17s

# Round-2 isolation: both file orders
python3 -m pytest -q -p no:cacheprovider -p no:randomly tests/api/test_rbac.py tests/api/test_public_demo_security.py → 25 passed
python3 -m pytest -q -p no:cacheprovider -p no:randomly tests/api/test_public_demo_security.py tests/api/test_rbac.py → 25 passed

# Round-2 ambient-secret pollution proof
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y PUBLIC_DEMO=1 python3 -m pytest -q -p no:cacheprovider tests/api/test_public_demo_security.py tests/lakebase/test_public_demo_write_guard.py → 29 passed

# Manual attacks (raw ASGI, no URL normalization) under /tmp/qp1-attack/
#   → demo value matrix, secret-gap matrix, 405/413/429 header dump, path traversal,
#     //api/ and /%2fapi/ evasion, chunked-body, health→db.lakebase import — all as above.
```

## Verdict

CHANGES_REQUESTED — fix the two blocking findings (demo-mode `/api/health` must not
import/touch `db.lakebase`; add a fail-closed guard so the public service cannot run
open when `PUBLIC_DEMO` is absent). The non-blocking notes (security headers on error
responses, secret-family breadth, streamed-body limit, proxy-aware rate limiting) are
recommended before public launch but do not individually block the slice.
```
===VERDICT END===
