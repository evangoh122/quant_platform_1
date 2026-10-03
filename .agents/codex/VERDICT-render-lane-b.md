===CODEX VERDICT START===

# CHANGES_REQUESTED

DeepSeek prerequisite: confirmed `.agents/deepseek/VERDICT-render-lane-b-check2.md` says APPROVED.

## Blocking findings

1. `api/main.py:135-146` — one client can exhaust the global limiter and deny service to everyone.

   The global counter is incremented before checking the per-IP limit. Consequently, requests already rejected by the 60-request client limit continue consuming the 600-request global allowance.

   Direct proof:

   ```text
   600 requests from attacker
   victim_after_attacker = (False, 55)
   global_count = 601
   ```

   A single IP can therefore make 600 inexpensive requests and cause an unrelated client’s first request to receive 429.

   Fix: enforce the per-IP limit first and charge the global counter only for requests that pass it. Prefer an edge/distributed limiter for the shared capacity limit. Add a regression test proving unlimited rejected requests from one IP cannot globally throttle another IP.

2. `api/main.py:116-146` — the advertised LRU bound does not bound `_counts`.

   Evicting an IP from `_lru` at lines 142-143 does not delete that IP’s `(ip, window)` entry from `_counts`. Direct construction with `lru_max=5` and 1,000 distinct IPs produced:

   ```text
   lru_keys = 5
   count_entries = 1000
   ```

   The default global ceiling limits practical growth per window, but the limiter is not structurally bounded by `RATE_LIMIT_LRU_MAX`, and increasing/disabling the global ceiling makes the discrepancy arbitrarily large.

   The test at `tests/api/test_public_demo_security.py:611-631` checks only `key_count`, masking this defect.

   Fix: have LRU eviction return the evicted IP and remove all corresponding `_counts` entries, or store counters directly in one bounded cache. Assert both `key_count` and `len(_counts)` remain within the configured bound.

## Independent security review

- Write routes: demo route enumeration contains only the four read routers plus the SPA GET route. All seven public `agent.tools_write` functions independently raised `PublicDemoWriteDisabled` before performing work.
- Identity: `get_current_user` returns `public-demo/viewer/authenticated=False` before reading the identity header. No header variant changed the result.
- Lakebase/subprocess: direct clean-environment probes of health and the `/tmp` SPA catch-all loaded neither `db.lakebase` nor `agent.tools_write`; patched `subprocess.run` was not invoked.
- Render fail-closed: `RENDER=true` without demo raised `PublicDemoConfigurationError`. Tested odd values including `t`, `1.0`, `maybe`, `2`, `yesplease`, and `enabled`; all raised.
- XFF: rightmost selection is defensible for Render’s current proxy behavior because client-supplied entries occupy the spoofable left side. Render’s guidance also warns against trusting the leftmost value. [Render guidance](https://render.com/articles/host-pocketbase-on-render)
- Secret gaps: non-empty `AWS_ACCESS_KEY_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, `GITHUB_PAT`, `REDIS_URL`, `MONGODB_URI`, `SENTRY_DSN`, `STRIPE_APIKEY`, `SECRET_KEY_BASE`, `AZURE_CLIENT_ID`, and generic `CREDENTIALS` passed validation. The Render allow-list itself is exact-name based and not excessively broad. These gaps are defense-in-depth unless the intended policy is literally “no credential-bearing environment variables.”
- Errors: tested/public-demo error responses contain sanitized fixed details; no stack traces, exception messages, or internal paths were found.

## Mutation proofs

All mutations were made only in `/tmp`:

- Registered `POST /api/mutation-write`: `test_demo_routes_methods_and_prohibited_paths` failed with `allows {'POST'}`.
- Removed the health demo gate: focused health safety test failed because Lakebase was imported and dependency detail became `AssertionError` instead of `disabled in public demo`.
- Removed the Render fail-closed guard: `test_render_without_public_demo_refuses` failed with `DID NOT RAISE PublicDemoConfigurationError`.

## Test execution

The requested command could not run because `tests/render` does not exist:

```text
ERROR: file or directory not found: tests/render
```

The permitted `tests/api` fallback collected successfully but stalled on its first `TestClient` request in this sandbox. The targeted non-HTTP configuration subset completed:

```text
51 passed in 0.52s
```

The worktree remains clean and unchanged.

===CODEX VERDICT END===
