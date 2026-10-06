# VERDICT: xbrl-pr42-fixes-r4 — MiMo
**Status:** APPROVED
**Round:** 4

## Changes
- `pipelines/ingest_sec_companyfacts.py`: Added keyword-only `max_workers: int = 4` argument to `run_ingest_companyfacts`. Rejects `< 1` with `ValueError("max_workers must be >= 1")`. Derives `worker_count = min(max_workers, len(ticker_cik_pairs))` (or 1 when no pairs). Passes `worker_count` to `ThreadPoolExecutor` — does not shadow the input.
- `tests/bronze/test_sec_companyfacts.py`: Updated `test_first_write_failure_allows_second_write` and `test_duplicate_manifest_attempt_count_with_retries` to pass `max_workers=1` for deterministic ordering. Updated `test_concurrent_duplicate_reservation_prevents_double_append` to pass `max_workers=2`. Added `test_max_workers_one_uses_single_worker` (ThreadPoolExecutor spy with 2 tickers) and `test_max_workers_zero_raises` (ValueError coverage).

## Commit
`78e6947` on `feat/xbrl-fundamentals`

## Blocking findings
None.

## Non-blocking notes
- The broader test suite (`-m "not spark and not lakebase and not databricks"`, 2737 tests) times out in CI-level runs; the specific file passes 94/94.

## Checks run
- `python3 -m pytest -q tests/bronze/test_sec_companyfacts.py` → 94 passed
- Before-fix proof: new tests fail with `TypeError: got an unexpected keyword argument 'max_workers'` on original code (git stash + copy new tests only)
- Mutation proof 1: `worker_count = min(4, len(...))` → spy test fails `assert 2 == 1`
- Mutation proof 2: reservation after Delta append → concurrent test fails `assert 2 == 1`
- `python3 -m pytest -q tests/bronze/test_sec_companyfacts.py -k "first_write_failure_allows_second_write or duplicate_manifest_attempt_count_with_retries"` × 30 → 60/60 passed
- `git diff --check` → clean (no trailing whitespace)