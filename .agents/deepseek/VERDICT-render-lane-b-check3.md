===VERDICT START===
# VERDICT: render-lane-b — DeepSeek (security lane, round-4 re-check)

**Status:** CHANGES_REQUESTED
**Round:** 3 (re-check per `CHECK-render-lane-b.md`, targeting `88ca7b8`; HEAD `15a0191`)
**Branch:** `slice/render-lane-b`

Both Codex round-4 findings are correctly fixed and the broadened secret check does not
false-positive on Render defaults — I verified all three with independent attacks, not just the
regression tests. However, I found a **pre-existing, unauthenticated path-traversal** in the SPA
catch-all that directly answers the "Could the catch-all ever shadow or expose anything?" attack
and must be fixed before this slice can ship as a public demo.

## Blocking findings

- **[api/main.py:219-221] SPA catch-all `/{full_path:path}` serves arbitrary files via
  percent-encoded `..` traversal.** `candidate = FRONTEND_DIST / full_path` is never confined to
  `FRONTEND_DIST`. `full_path` arrives **decoded** from the ASGI scope (Starlette decodes
  `%2e%2e` → `..`), so `GET /%2e%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd` yields
  `candidate = <dist>/../../../../etc/passwd = /etc/passwd`, `is_file()` is true, and
  `FileResponse` returns it with 200. Confirmed against a real uvicorn server (not just TestClient):

  ```
  GET /../../../../../../etc/passwd                                -> 200  root:x:0:0:root:/root:/bin/bash…   (LEAK)
  GET /%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd               -> 200  root:x:0:0:root:/root:/bin/bash…   (LEAK)
  GET /                                                            -> 200  INDEXHTML                           (ok)
  ```

  Impact: unauthenticated arbitrary file read (`.env`, source, `/etc/passwd`) on the public
  internet-facing demo — which defeats the entire secret-validation posture this slice exists to
  provide. The leak is **not** rate-limited (the path does not begin `/api`, so it skips the
  per-IP limiter and method guard). It is reachable in both demo and non-demo mode because the
  SPA mount sits outside the `if not demo` branch. The adjacent `/assets` `StaticFiles` mount is
  safe (built-in `..` protection) — only the hand-rolled `_spa` fallback is vulnerable.

  Fix: confine the resolved path, e.g.
  `candidate = (FRONTEND_DIST / full_path).resolve()` then require
  `candidate.is_relative_to(FRONTEND_DIST.resolve())` before `FileResponse`, or reject any
  `full_path` whose decoded segments contain `..`. Add a regression test asserting that
  `%2e%2e` and `..` segments return `index.html` (or 404) and never file contents.

This is a lane-B-owned file (`api/main.py`) and a public-demo exposure, so it is in-scope for this
slice. It predates round 4 (not introduced by `88ca7b8`) but ships with the demo and cannot wait.

## Round-4 items — verified fixed (not regressed)

- **Per-IP checked before global** (Codex #1). `check()` now enforces the per-IP limit first and
  charges `_global_counts` only for requests that pass it. Manual proof: `limit=5, global_limit=20`,
  50 requests from one IP → `check("victim")` returns `(True, 0)`; the same attacker IP is blocked
  (`False`). The old code would have given the victim a 429.
- **One bounded structure** (Codex #2). Single `OrderedDict[ip] -> (window, count)` replaces the
  dual `_lru`+`_counts`. Manual proof: `lru_max=5`, 1,000 distinct IPs → `key_count == 5` and
  `len(_counts) == 5`. `_global_counts` is keyed by `window_ts` and cleaned by `_cleanup`, so it is
  bounded (~2–3 entries), not 1,000.
- **Broadened secret families + no Render false positive.** All new prefixes
  (`AWS_/AZURE_/GOOGLE_/GCP_/GITHUB_/GH_/STRIPE_/SENTRY_`), suffixes
  (`_DSN/_URI/_PAT/_APIKEY/_CREDENTIALS/_KEY_BASE`), exact names (`CREDENTIALS/REDIS_URL/
  MONGODB_URI/SECRET_KEY_BASE`), and the `*_URL`-with-embedded-credentials rule reject as expected.
  I enumerated 22 harmless Render/clean values (`RENDER*`, `PORT`, `PYTHON_VERSION`, `NODE_VERSION`,
  `PATH`, `HOME`, `API_URL`, `WEBHOOK_URL`, `SIGNUP_URL`, etc.) → **zero false positives**. Values
  never leak into error text (`"SUPERSECRETVALUE123" not in str(e)`).

## Re-run of earlier attacks — no regression

- Demo value matrix: `true/ 1 /TRUE/yes/on` → on; `0/""/false/no/off` → off; `t/1.0/maybe/2/
  yesplease/enabled` → raises `PublicDemoConfigurationError`. Env var read at call time, `create_app()`
  re-reads it.
- Write reach: POST/PUT/PATCH/DELETE → 405 on `/api/orders` and `//api`, `/%2fapi`, `/API`,
  `/api//`, `/a%70i`; method-override headers (`X-HTTP-Method-Override`, `X-Method-Override`) → 405.
  `db.lakebase`, `agent.tools_write`, `execution.bridge`, `ib_insync`, `ibapi` all absent from
  `sys.modules` after app construction + requests.
- All 7 write tools raise `PublicDemoWriteDisabled` before `get_lakebase`/`IBKRBridge`/`RiskEngine`/
  market clock are touched.
- `/openapi.json`, `/docs`, `/redoc` → 404. Spoofed `x-forwarded-email` → byte-identical response.
- Security headers (`nosniff`, `XFO: DENY`, CSP, `Cache-Control: no-store`) present on 200/405/429/413;
  CORS absent in demo even with `CORS_ORIGINS` set.
- `RENDER` set without demo → `PublicDemoConfigurationError("refusing to start…")`;
  `LAKEBASE_HOST` set in demo → raises with name-only error.
- `/api/health` → 200 in ~4 ms, `db.lakebase` never imported, no subprocess.

## Non-blocking notes

- **[api/main.py:238-266] HEAD/OPTIONS on GET-only demo routes return FastAPI's 405 (`allow: GET`).**
  The middleware correctly allows GET/HEAD/OPTIONS through; the 405 comes from the router because no
  demo route defines HEAD/OPTIONS. Not a security bug (headers are still applied), but the spec's
  "GET/HEAD/OPTIONS" wording is only half-true in practice. Pre-existing; unchanged by round 4.
- **[api/main.py:268-276] Streamed/chunked body size is still unbounded** (only `Content-Length`
  is checked). Pre-existing; no demo route consumes a body, so no practical impact.
- **[api/main.py:279-287] Request timeout does not bound a hung handler** (`asyncio.wait_for`
  returns 504 only after the handler completes). Pre-existing; no demo route performs blocking I/O.
- **`*_URL` credential heuristic** keys on `@` or `://user:`; a user-set harmless `*_URL` whose value
  contains `@` (e.g. `?email=user@example.com`) would be a fail-closed false positive. No Render
  default triggers it (`RENDER_EXTERNAL_URL` is allow-listed), so non-blocking.

## Checks run

```
PUBLIC_DEMO=1 python3 -m pytest -q -p no:cacheprovider tests/api/test_public_demo_security.py tests/lakebase/test_public_demo_write_guard.py
  → 117 passed

python3 -m pytest -q -p no:cacheprovider tests/api tests/lakebase/test_guardrails.py tests/lakebase/test_execution_boundary.py
  → 155 passed

python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
  → 589 passed, 67 skipped

CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y AWS_ACCESS_KEY_ID=x OPENAI_API_KEY=x \
  python3 -m pytest -q -p no:cacheprovider tests/api
  → 118 passed

Manual attacks (scratch in /tmp only; worktree left clean):
  A1/A2 limiter ordering + LRU bound; A3 secret false-positive matrix (22 clean values → 0 FP);
  A4 secret rejection matrix; A6 value-leak check; A7 demo value matrix; A8 path normalisation;
  B1-B12 HTTP write/method/identity/module/headers/CORS; C1 413 via oversized GET CL; C4 7-tool
  write guard; path-traversal probe via uvicorn (LEAK reproduced).
```

## Verdict

CHANGES_REQUESTED — the round-4 limiter and secret fixes are correct and non-regressing, but the
SPA catch-all path traversal (api/main.py:219-221) is an unauthenticated arbitrary-file-read on the
public demo and must be fixed (plus a regression test) before this slice can be approved for PR.
The fix is a one-line path-confinement change.
===VERDICT END===
