===VERDICT START===
# VERDICT: xbrl-B1a-r4 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 4

## Blocking findings

- [tests/bronze/test_sec_companyfacts.py:1076] `test_concurrent_attempt_count_per_cik`
  does NOT detect the shared-counter regression it was added to guard. A faithful revert of
  the per-call attempt fix (restore `attempt_count = client.request_count - req_before` at
  the call site and in both `except` blocks, i.e. the exact c2ab7aa pre-fix state of
  `pipelines/ingest_sec_companyfacts.py` + `pipelines/sec_rag_ingest.py`) leaves the entire
  file green: **54 passed**. The two "concurrent" fetches never actually overlap in a way
  that contaminates the shared counter (the 429 → cooldown/sleep → retry sequence
  serializes the second fetch), so the shared counter coincidentally yields the same 2/1
  counts the test asserts. The CHECK request's mutation "attempt_count from shared
  client.request_count deltas" therefore does NOT fail a test.

- [pipelines/ingest_sec_companyfacts.py:458] The duplicate-manifest fix
  `manifest.attempt_count = attempt_count` (skipped_duplicate branch) is present but has NO
  mutation-proof test. No test asserts the `skipped_duplicate` entry's attempt_count
  (grep: only `test_same_payload_skipped_within_run` checks `skipped_duplicate_payloads == 1`
  and `fetch_status`, never `attempt_count`; the fixture fetches use no retries so the
  computed value equals the dataclass default `1`). Mutation (drop the assignment) →
  **54 passed**. The CHECK request's mutation "duplicate manifests with default
  attempt_count" therefore does NOT fail a test.

## Confirmed fixed (round-4 blocking items + item #5)

- [pipelines/sec_rag_ingest.py:156-190] `_validate_user_agent` no longer interpolates the
  UA value into any error message (all three `ValueError`s are fixed strings). `grep` for
  `repr(user_agent)`/`str(user_agent)`/f-string of `user_agent` in error/log paths → none.
  Mutation (re-add `"Got: " + repr(user_agent)`) → `test_error_message_does_not_leak_ua_value`
  **FAILS** (`'AdminContact@company-domain.com' is contained here: ... Got: '...'`).
- [tests/bronze/test_sec_companyfacts.py:746] `test_first_write_failure_allows_second_write`
  is now mutation-proof: mutation (move `seen_payloads.add` before `delta_writer`) →
  **1 failed** (`assert result["fetched_count"] == 1` → `assert 0 == 1`), deterministic
  **40/40** runs.
- [tests/bronze/test_sec_companyfacts.py:1208] `test_bounded_concurrency_max_workers`
  captures `max_workers` via a tracking `ThreadPoolExecutor` and asserts `all(mw <= 4)`.
  Mutation (`min(4,…)` → `min(16,…)`) → **1 failed**.

## Thread-safety answer

The per-call attempt tracking IS thread-safe. `_fetch_one` allocates a fresh
`call_attempts = [0]` list per task (one per `ThreadPoolExecutor` worker thread), passed by
reference through `fetch_company_facts → _fetch_raw_bytes → SecClient._request`, which does
`_attempts[0] += 1`. Each list is owned by a single thread, so no cross-thread sharing or
data race on the count. The shared `self._request_count += 1` remains but is only the
diagnostic `request_count` property and no longer feeds `attempt_count`.

## Non-blocking notes

- [tests/bronze/test_sec_companyfacts.py:750] Docstring claims "sequential execution
  (`max_workers=1`)" but the test maps two tickers to one CIK, so `max_workers = min(4, 2) =
  2`. The test is still mutation-proof (every race outcome yields `fetched_count != 1`), so
  this is a doc inaccuracy, not a defect.
- MiMo's `.agents/mimo/VERDICT-xbrl-B1a-r4.md` APPROVED self-report overstates completion:
  items #3 and #4 are code-correct but their mutation-proof tests are respectively
  ineffective and absent (blocking findings above). The two blocking items (#1, #2) and
  item #5 are genuinely done.

## Checks run

- `python3 -m pytest tests/bronze/test_sec_companyfacts.py tests/rag/test_sec_rag_ingest.py -q` → **257 passed**
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **2492 passed, 107 skipped, 24 deselected** (218.12s)
- Mutation "re-add `repr(user_agent)` in UA error" → **1 failed**
- Mutation "move `seen_payloads.add` before write" → **1 failed** (40/40 runs)
- Mutation "faithful revert to shared `client.request_count` deltas" (c2ab7aa pipeline state) → **54 passed** ← not caught
- Mutation "drop `manifest.attempt_count` on duplicate manifest" → **54 passed** ← not caught
- Mutation "`max_workers` cap 4→16" → **1 failed**
- `grep` for `repr(user_agent)` / `str(user_agent)` / f-string UA in error/log paths → none
- Earlier B1a inline mutation tests (`test_mutation_accept_placeholder_ua`,
  `test_mutation_malformed_fact_not_dropped`, `test_mutation_rate_limiter_max_enforced`,
  `test_mutation_403_not_retried`, `test_manifest_http_status_*`, `test_*_no_overwrite`) →
  all green.
===VERDICT END===
