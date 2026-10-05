===VERDICT START===
# VERDICT: app-resilience-round11b — DeepSeek (checker)
**Status:** APPROVED
**Round:** 11b (check)
**Range:** 3718ab6 (fix(warehouse): semaphore released only by the worker once started …) on slice/app-resilience-round11

Re-check of my two round-11 blocking findings against Claude's tiny fix. Both are resolved.

## Blocking findings

None.

## Findings re-verified (previously blocking, now fixed)

1. **Semaphore double-release (round-11 finding #1) — FIXED.**
   `db/delta_adapter.py:228` introduces `worker_started = False`; it is set to `True`
   only after `t.start()` (`db/delta_adapter.py:260`). The outer `except BaseException`
   now releases only when `not worker_started` (`db/delta_adapter.py:288-289`), so the
   worker's own `finally` (`db/delta_adapter.py:256`) is the sole release once the
   thread has started — including the timeout path, where the worker is still running
   and would previously have released the slot a second time.
   **Path accounting (instrumented, semaphore=2):**
   - normal completion → 2→2 (exactly one acquire/one release)
   - worker error → 2→2
   - timeout + late completion → 2→1 (slot held while worker hung) → 2 after the
     worker returns (released exactly once, no leak, no over-release)
   - exception before thread start (`stage.__enter__` raises) → 2→2 and
     `RuntimeError` propagates cleanly — **no `NameError` on `t`** (the except block
     now references `worker_started`, defined at :228, never `t`).

2. **Token-mint timeout test did not drive production (round-11 finding #2) — FIXED.**
   `tests/api/test_resilience.py:428-450` now calls production `lb.mint_token_via_cli("test-instance")`
   directly (`:449`) and monkeypatches `lb.subprocess.run` (`:446`), asserting the
   production call passes `0 < timeout <= LAKEBASE_CONNECT_TIMEOUT + 2` (`:450`).
   The fake raises `TimeoutExpired` only when a timeout is present, so a dropped
   `timeout=` in production fails the test. Dead `_slow_mint`/`_mint_with_timeout` are gone.

## Mutation re-runs (archive copies via `git archive HEAD | tar -x -C /tmp/qp1-mut`)

- **M1 remove semaphore acquire** (`db/delta_adapter.py:222` `if not _query_semaphore.acquire(...)` → `if False:`)
  → `test_warehouse_query_semaphore_bounded` **FAILED** (max_concurrent > 2). Killed.
- **M2 drop mint timeout** (delete `timeout=LAKEBASE_CONNECT_TIMEOUT + 2` at `db/lakebase.py:65`)
  → `test_token_mint_subprocess_timeout` **FAILED** (`AssertionError: subprocess.run called without timeout=`). Killed.

## Flakiness check

- `test_warehouse_query_semaphore_bounded` × 5 → **5/5 passed** (1.62–1.72 s each).

## Checks run

- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` (WSL)
  → **1550 passed, 97 skipped, 24 deselected, 44 warnings** in 204.25 s (0 failed).
- `python3 -m pytest -q tests/api/test_resilience.py::test_token_mint_subprocess_timeout
  tests/api/test_health_diagnostics.py::test_warehouse_query_semaphore_timeout
  tests/api/test_health_diagnostics.py::test_warehouse_query_calls_cancel_on_timeout`
  → **3 passed** in 2.76 s.
- `python3 -m pytest -q tests/api/test_health_diagnostics.py::test_warehouse_query_semaphore_bounded` × 5 → **5 passed**.

## Non-blocking notes

- None.
===VERDICT END===
