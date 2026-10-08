# VERDICT: xbrl-pr42-fixes-r7 — MiMo
**Status:** APPROVED
**Round:** 7

## Blocking findings
None.

## Non-blocking notes
- Timeout on `key_cond.wait()` set to 10s as a safety net; production owner always notifies within milliseconds.
- The `TimeoutCondition` in the test is a test-only mechanism to detect missing notifications without hanging the suite.

## Implementation summary

### Per-key in-flight/completed coordination (`ingest_sec_companyfacts.py`)
- Replaced plain `seen_payloads` set with `key_state` dict + `key_cond` Condition.
- States: `in_flight` → `completed` or `failed`.
- Duplicate arriving while in-flight calls `key_cond.wait()` and re-checks state after wake.
- On owner success: `key_state[key] = "completed"` + `notify_all()` → waiters record `skipped_duplicate`.
- On owner failure: `key_state[key] = "failed"` + `notify_all()` → exactly one waiter acquires ownership for retry.
- Timeout on `wait()` (10s) prevents indefinite hang if notification is missed.
- Outer exception handlers also manage key state for fetch-level failures (SecClientError, unexpected).

### Synchronized regression test (`test_sec_companyfacts.py`)
- `test_concurrent_failure_recovery_second_worker_retries`: first worker owns append and blocks, second worker waits on key_cond, first append fails (injected RuntimeError), second worker wakes, retries, and succeeds.
- Uses `threading.Event` for deterministic synchronization.
- `TimeoutCondition` wrapper adds 15s timeout to first `wait()` call to detect missing notifications.
- Assertions: exactly 2 append attempts, exactly 1 success, no `skipped_duplicate`.

### Whitespace cleanup (`sec_rag_ingest.py`)
- Removed trailing whitespace at lines 1286 and 1293.

### Mutation proofs
1. **M1** (immediate skipped_duplicate for in-flight key): New test fails — proves wait-before-skip is required.
2. **M2** (mark completed before delta_writer): New test fails — proves state must transition after write.
3. **M3** (omit failure-state release): New test times out — proves state transition is required for waiter to proceed.

## Checks run
- `python3 -m pytest -q tests/test_jobs_serverless.py` → 16 passed
- `python3 -m pytest -q tests/bronze/test_sec_companyfacts.py` → 98 passed (including new test)
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → 2672 passed, 107 skipped
- `git diff --check` → no whitespace issues
- Mutation proofs (M1, M2, M3) → all 3 PASS