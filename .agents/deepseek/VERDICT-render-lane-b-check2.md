===VERDICT START===
# VERDICT: render-lane-b — DeepSeek (security lane, round-3 re-check)

**Status:** APPROVED
**Round:** 2 (re-check per `CHECK-render-lane-b.md`, targeting `5282117`)
**Branch:** `slice/render-lane-b` (HEAD `0524c91`, re-checked commit `5282117`)

I re-ran the security-lane attacks against the round-3 fixes. Scratch work lived under
`/tmp` only; the worktree was not modified. All round-1 blocking findings and the
round-3 REQUIRED items are correctly fixed. No new blocking issue found; the notes
below are defense-in-depth / test-quality gaps only.

## Blocking findings

None.

## What I verified as fixed (round-3)

- **`/api/health` in demo** — `GET /api/health` returns `200` in 0.02 s with both
  dependencies reported `{"ok": false, "detail": "disabled in public demo"}`; `db.lakebase`
  is never imported and `subprocess.run` never invoked (patched to raise).
- **Fail-closed default** — `RENDER=true` without `PUBLIC_DEMO` raises
  `PublicDemoConfigurationError("refusing to start with write routes on Render...")` at
  import; `RENDER=true PUBLIC_DEMO=1` starts with 4 demo routers and `openapi_url=None`;
  unset env builds the full non-demo app (`/openapi.json` present). Unrecognised non-empty
  `PUBLIC_DEMO` (`t`, `1.0`, `0.0`, `maybe`, `2`, `yesplease`) raises; `"0"`/`"false"`/`"no"`
  are still off, `" 1 "`/`"TRUE"`/`"yes"`/`"on"` are on.
- **Security headers on every response** — `X-Content-Type-Options`, `Referrer-Policy`,
  `X-Frame-Options`, `Content-Security-Policy`, and `Cache-Control: no-store` are present on
  200, 405, 413, 429, and 504 (verified by direct request; no missing headers on any status).
- **Broadened secret families** — `*_PASSWORD`, `*_KEY`, `*_PASS`, `*_PWD` suffixes;
  `PG`, `POSTGRES_`, `IBKR_`, `POLYGON_`, `OPENAI_`, `ANTHROPIC_` prefixes; exact
  `DATABASE_URL`, `HF_TOKEN` all reject at construction with names-only error text
  (confirmed `super-secret-value-12345` never leaks). The Render allow-list
  (`RENDER*`, `PORT`, `PYTHON_VERSION`, `NODE_VERSION`, `PATH`, `HOME`) contains nothing
  sensitive.
- **Rate limiter** — keys on the rightmost `X-Forwarded-For` when `RENDER` is set (spoofed
  leftmost entry does not open a new bucket; two rightmost IPs get separate buckets); LRU cap
  (verified `key_count <= cap` under 10 distinct IPs with `RATE_LIMIT_LRU_MAX=5`); global
  ceiling 600/min backstops and, together with the 60 s cleanup, bounds `_counts` growth.
- **Path normalisation** — `//api/orders`, `/%2fapi/orders`, `/%2Fapi/orders`,
  `/API/orders`, `/api//orders`, `/a%70i/orders` all → middleware 405 (with headers).
- **Route enumeration test is non-vacuous** — mutation (registering `POST /api/evil` on a
  demo app) is detected by the same `include_context.prefix` walk used in the test.

## Non-blocking notes

- **[api/main.py:283-287] The request timeout does not bound execution time.**
  `asyncio.wait_for(call_next, timeout=…)` returns 504 only *after* the downstream handler
  completes; for a handler that hangs forever it never returns. Measured:
  `sleep(5)`/`timeout 1` → 504 at 5.02 s; `sleep(1000)`/`timeout 2` → no 504 within 20 s
  (both `TestClient` and `httpx.ASGITransport`). This is pre-existing (round 1), not a
  round-3 regression. Practical impact in demo is nil: no registered demo route performs
  blocking I/O — `health` short-circuits, `signals`/`market` hit `read_delta` with no
  `snapshot_key` and return before touching `api.demo_data`/spark (and `api.demo_data`
  does not exist yet), `analytics` returns static empty envelopes. The 504 response still
  carries correct headers and no exception detail. Recommend a future pass that bounds
  handler time for real (e.g. an outer `asyncio.timeout` scope around the route, or
  cancelling the downstream task group), but this does not block the slice.
- **[tests/api/test_public_demo_security.py:70-90] `test_no_lakebase_import_in_demo` does
  not actually hit "every registered GET route".** `_get_api_get_routes` requires a truthy
  route `path`, so routes registered at `""` (`health`, `signals`, `analytics`) are skipped
  and only `/api/market/{symbol}` is enumerated. `health` is covered separately by
  `test_health_returns_200_fast_in_demo`; `signals` and `analytics` are not exercised by that
  test. The routes themselves are safe — I confirmed all four GET routes return 200 with none
  of `db.lakebase`, `db.delta_adapter`, or `agent.tools_retrieval` in `sys.modules`. This is a
  coverage gap, not a vulnerability, but it means the round-3 "hit EVERY registered GET
  route" requirement is only partially satisfied.
- **[tests/api/test_public_demo_security.py:449-467] The 413 test is near-vacuous.** In demo,
  the method guard (405) fires before the body-size check, so an oversized `POST` returns
  405, and `test_security_headers_on_413`'s `if resp.status_code == 413` branch never runs.
  The 413 path is only reachable via GET/HEAD/OPTIONS with an oversized `Content-Length`
  (verified: `GET` with `Content-Length: 2000000` → 413 with all headers). Functional
  behavior is correct; the test simply doesn't exercise it. Consider a `client.get` with an
  oversized `Content-Length` to make the 413 assertion real.
- **[api/main.py:279-282] Streamed/chunked body size is still unbounded.** Only
  `Content-Length` is checked; a chunked body with no length is not size-capped. Pre-existing
  and outside the round-3 REQUIRED list. No demo route consumes request bodies, so no
  practical impact; flagging for completeness against the original spec's "from streamed
  bytes" wording.
- **Cosmetic:** `api/demo.py` has no trailing newline; `_LRUCache` evicts by insertion order
  (no `move_to_end` on lookup hits), so it is a cap rather than a true LRU — still bounded,
  so not a security concern.

## Checks run

```
# Re-check acceptance (demo security + write guard)
PUBLIC_DEMO=1 python3 -m pytest -q -p no:cacheprovider tests/api/test_public_demo_security.py tests/lakebase/test_public_demo_write_guard.py
  → 77 passed

# Non-demo API + lakebase boundary
python3 -m pytest -q -p no:cacheprovider tests/api tests/lakebase/test_guardrails.py tests/lakebase/test_execution_boundary.py
  → 115 passed

# CHECK command: full suite excluding lakebase
python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
  → 549 passed, 67 skipped

# Round-2 ambient-secret isolation (WSL shell carries tokens)
CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q -p no:cacheprovider tests/api
  → 78 passed

# Round-2 isolation, both file orders
python3 -m pytest -q -p no:cacheprovider -p no:randomly tests/api/test_rbac.py tests/api/test_public_demo_security.py
  → 73 passed
python3 -m pytest -q -p no:cacheprovider -p no:randomly tests/api/test_public_demo_security.py tests/api/test_rbac.py
  → 73 passed

# Manual attacks (scratch in /tmp)
#   demo value matrix ("true"," 1 ","TRUE","yes","on","0","","false","no","off","t","1.0",...)
#   health: no lakebase import / no subprocess / 0.02 s
#   headers on 200/405/413/429/504 (all present)
#   timeout bounding (504 only after handler completes; never on infinite hang)
#   //api, /%2fapi, /%2Fapi, /API, /api//, /a%70i → 405
#   all 4 GET routes: no db.lakebase/db.delta_adapter/agent.tools_retrieval import
#   route-enumeration mutation (POST /api/evil) → detected
#   RENDER fail-closed via create_app / import (3 cases)
#   git show 5282117 grep for secrets → none
```

## Verdict

APPROVED — round-3 fixes close both round-1 blocking findings and all REQUIRED items.
Remaining notes are defense-in-depth/test-quality gaps with no exploitable path in demo mode
(no demo route does blocking I/O or consumes a body; identity spoofing, write reach, and
secret-variable leak are all closed). Recommend addressing the request-timeout bound and the
route-enumeration coverage in a follow-up, but neither blocks this slice.
===VERDICT END===
