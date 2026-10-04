# VERDICT: app-resilience-round11 — DeepSeek (checker)

**Status:** CHANGES_REQUESTED
**Round:** 11 (check)

===VERDICT START===

## Scope

Read-only check of round 11 (`99eab8b..94ec685`, HEAD `0a7397a`) against my r9-10
verdict. Re-ran my four surviving mutations in `git archive HEAD` copies, verified
the query-constant refactor produced byte-identical SQL, and ran the full suite.

**Result: 3 of 4 of my r9-10 mutations are now caught, but the item-2 test change
exposed a genuine production double-release bug (full suite has 1 failure), and the
new token-mint timeout test does not actually guard production code.**

## Blocking findings

1. **[Critical] Full suite fails: `test_warehouse_query_semaphore_bounded` fails on
   CORRECT production code — semaphore double-release.**
   `db/delta_adapter.py:286-288` releases the semaphore in the `except BaseException`
   block whenever `t.is_alive()` — i.e. exactly when a query times out and the worker
   is *still running*. The worker later releases the same slot again in its own
   `finally` (`db/delta_adapter.py:255`). Two releases for one acquire. Result: a
   stuck query releases its slot while still in flight, so concurrent queries exceed
   `_MAX_CONCURRENT_QUERIES` — precisely the pile-up the semaphore is meant to prevent.
   The round-11 shared counter (`state["max"]`) now measures this honestly and the
   assertion `state["max"] == 2` fails: observed `max == 3` or `4` (non-deterministic
   race; failed 5/5 runs in WSL). Acceptance "0 failed" is not met.
   - `python3 -m pytest -q -m "not spark and not lakebase and not databricks"`
     → **1 failed, 1549 passed, 97 skipped, 24 deselected** in 214.93 s.
     The single failure is `tests/api/test_health_diagnostics.py::test_warehouse_query_semaphore_bounded`.
   - This is NOT an environment issue: the item-2 mutation (remove acquire at
     `db/delta_adapter.py:222`) does push `max` to 6 and fails too, but the test
     *also* fails on correct code, so it is not a clean guard. MiMo's r11 verdict
     dismissed this as "pre-existing env" — incorrect; it is a production logic bug
     introduced in `0148070` ("release semaphore in worker finally"), not in round 11.

2. **[Test-strength gap] Token-mint timeout test does not guard production.**
   `tests/api/test_resilience.py:428-475` (`test_token_mint_subprocess_timeout`) never
   calls production `mint_token_via_cli`. It constructs `LakebaseToken` with a *local*
   `_mint_with_timeout` (`:450`) whose own `subprocess.run(..., timeout=...)` (`:464`)
   is hardcoded and unrelated to `db/lakebase.py:65`. I mutated production to drop
   `timeout=` from `mint_token_via_cli` (`db/lakebase.py:65`) and the test still
   passed (1 passed). The BUILD item 1 acceptance "Mutation: drop `timeout=` → FAIL"
   **survives**. (`_slow_mint` at `:436-444` is also dead code, never invoked.)

## Findings that ARE now fixed (mutation re-runs)

- **[1] Lakebase pool open/closed** — FIXED. `test_pool_closed_without_open_raises`
  (`tests/api/test_resilience.py:372-423`) calls `_build_pool()` directly and asserts
  the raised exception is not `PoolClosed`. Mutation: delete `pool.open(wait=False)`
  (`db/lakebase.py:173`) → **FAILED** (`Got PoolClosed — pool.open() was not called`).
  (Note: `test_first_request_bounded_when_pool_hangs` alone still passes under the
  mutation — it exercises the graceful-degradation route — so the guard is the direct
  `_build_pool` test, which is correct.)
- **[4] Schema contract from REAL SQL** — FIXED. `validate_actual_queries()`
  (`db/schema_contract.py:186-257`) now imports the real builders from
  `delta_adapter`/`tools_retrieval`; the duplicated hardcoded SQL is gone. Mutation:
  add `"open"` to `_INTRADAY_COLS` (`db/delta_adapter.py:75`) →
  `test_actual_queries_match_contract` **FAILED** (2 errors: `open` not in contract).
- **[8] Requirements full-AST scan** — FIXED. `_scan_all_imports`
  (`tests/test_requirements_completeness.py:76-110`) walks the whole AST and adds
  `module.alias_name` (`from databricks import sql` → `databricks.sql`). Mutation:
  remove `databricks-sql-connector` from `requirements.txt` →
  `test_all_top_level_imports_declared_in_requirements` **FAILED**
  (`databricks.sql → databricks-sql-connector` missing).

## Query-constant refactor — SQL unchanged

Built the five production queries (latest_signals, market_features daily + intraday,
options, cot) by monkeypatching `_warehouse_query` to capture `(sql, params)` on both
the pre-refactor tree (`1333b53`) and HEAD, then diffed:

- `diff /tmp/pre_queries.txt /tmp/post_queries.txt` → **IDENTICAL** (byte-for-byte,
  all 5 queries and all params equal). No production SQL text or param changed.

## r9-10 PASS list — no regression

- `tests/test_smoke_app.py tests/test_app_yaml.py tests/test_requirements_completeness.py
  tests/api/test_frontend_serving.py tests/api/test_resilience.py tests/ml/test_ablation.py`
  → **33 passed** (smoke, app.yaml, requirements, env isolation, resilience, ablation
  timeout all still green). Full suite confirms only the single semaphore failure above.

## Checks run

- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` (WSL)
  → **1 failed, 1549 passed, 97 skipped, 24 deselected, 44 warnings** in 214.93 s.
- `test_warehouse_query_semaphore_bounded` × 5 → failed 5/5 (`max` 3,3,4,4,4).
- Mutation copies (via `git archive HEAD | tar -x -C /tmp/r11-mN`):
  - M1 drop `pool.open(wait=False)` → `test_pool_closed_without_open_raises` **FAILED** ✓
  - M2 remove semaphore acquire → `test_warehouse_query_semaphore_bounded` **FAILED**
    (max=6) — but also fails on correct code (max 3/4) ✗ (see blocking #1)
  - M3 add `open` to `_INTRADAY_COLS` → `test_actual_queries_match_contract` **FAILED** ✓
  - M4 drop `databricks-sql-connector` → `test_all_top_level_imports_declared_in_requirements` **FAILED** ✓
  - M5 drop `timeout=` from production `mint_token_via_cli` → `test_token_mint_subprocess_timeout` **PASSED (survived)** ✗ (see blocking #2)
- Working tree clean at end of check (`git status` → nothing to commit).

===VERDICT END===
