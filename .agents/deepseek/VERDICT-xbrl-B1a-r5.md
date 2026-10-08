===VERDICT START===
# VERDICT: xbrl-B1a-r5 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 5

Both round-4 blocking findings are now mutation-proof. The two new tests in
`07b2a87` genuinely fail under their target mutations, deterministically.

## Blocking findings

None.

## Confirmed fixed (round-4 blocking items #1 and #2)

- [tests/bronze/test_sec_companyfacts.py:1201] `test_concurrent_attempt_count_per_cik`
  is now barrier-based and mutation-proof. The exact r4 revert (restore shared
  `attempt_count = client.request_count - req_before` at the call site and in BOTH
  `except` blocks — i.e. the c2ab7aa pre-fix state of
  `pipelines/ingest_sec_companyfacts.py` + `pipelines/sec_rag_ingest.py`) makes the
  test **FAIL at line 1263** (`assert success_entries[0].attempt_count == 2`).
  **10/10 runs failed**, all at the same assertion — the `threading.Barrier(2)` forces
  CIK A (429→200) and CIK B (200) to reach `_http.get` simultaneously, so the shared
  counter is contaminated (A=3, B=2 instead of 2/1) on every run. The old timing-based
  serialization that masked this in r4 is gone.

- [tests/bronze/test_sec_companyfacts.py:801] `test_duplicate_manifest_attempt_count_with_retries`
  is new and mutation-proof. Removing `manifest.attempt_count = attempt_count` from the
  `skipped_duplicate` branch ([pipelines/ingest_sec_companyfacts.py:458]) makes the
  test **FAIL** (`assert skipped[0].attempt_count == 2` → `assert 1 == 2`, the
  dataclass default). The URL-routed deque (200, 429, 200) guarantees the skipped entry
  is the 2-attempt fetch regardless of which ticker wins the race, so the assertion is
  deterministic in both orderings.

## Re-verified (earlier B1a mutations still caught)

- m3 re-add `repr(user_agent)` in UA error → `test_error_message_does_not_leak_ua_value` **1 failed**
- m4 move `seen_payloads.add` before Delta write → `test_first_write_failure_allows_second_write` **1 failed**
- m5 `max_workers` cap 4→16 → `test_bounded_concurrency_max_workers` **1 failed**
- Inline B1a mutation tests (`-k 'mutation or no_overwrite or manifest_http_status'`) → **10 passed**

## Non-blocking notes

- [tests/bronze/test_sec_companyfacts.py:117] `BarrierFakeHttpClient.calls.append(...)`
  is outside the lock, but `calls` is a diagnostic list not asserted by any test —
  Python `list.append` is GIL-atomic, so no data race on results.
- The process-wide `get_global_limiter` singleton retains the first test's `FakeClock`
  (pre-existing, unchanged by this round); it did not affect determinism here — the
  concurrent test passed 5/5 at HEAD and the full suite is green.

## Checks run

- `python3 -m pytest tests/bronze/test_sec_companyfacts.py tests/rag/test_sec_rag_ingest.py -q` → **258 passed**
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **2493 passed, 107 skipped, 24 deselected** (224.58s)
- Mutation "shared counter revert" (m1, exact r4 revert) → `test_concurrent_attempt_count_per_cik` **10/10 FAILED**
- Mutation "drop duplicate attempt_count" (m2) → `test_duplicate_manifest_attempt_count_with_retries` **1 failed**
- `test_concurrent_attempt_count_per_cik` at unmutated HEAD → **5/5 passed** (not flaky)
- Mutations m3/m4/m5 → each **1 failed** (as above)
===VERDICT END===
