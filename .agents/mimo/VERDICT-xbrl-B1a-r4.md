===VERDICT START===
# VERDICT: xbrl-B1a-r4 — MiMo (builder)
**Status:** APPROVED
**Round:** 4

## Blocking findings

None. Both blocking items fixed.

## Non-blocking notes

- None remaining.

## Items completed

1. **Blocking #1 — UA error message leak** (`pipelines/sec_rag_ingest.py:187-189`)
   Removed `repr(user_agent)` from the format-check ValueError. Message now says only
   what's expected, never echoes the input. Mutation-proof test added
   (`test_error_message_does_not_leak_ua_value`): puts `repr` back → test fails because
   the input UA value appears in the message.

2. **Blocking #2 — seen_payloads mutation test** (`tests/bronze/test_sec_companyfacts.py:737-793`)
   Rewrote `test_first_write_failure_allows_second_write` to use sequential execution
   (`max_workers=1`) so the ordering is deterministic. First fetch fails at Delta write,
   second identical payload must still write. Mutation (`seen_payloads.add` before write)
   → `fetched_count == 0` instead of 1. Verified: mutation causes `assert 0 == 1`.

3. **Non-blocking #3 — per-call attempt_count** (`pipelines/ingest_sec_companyfacts.py:283-306`,
   `pipelines/sec_rag_ingest.py:826-836`)
   Added `_attempts: Optional[List[int]]` parameter to `SecClient._request`,
   `_fetch_raw_bytes`, and `fetch_company_facts`. Each HTTP request increments
   `_attempts[0]` alongside `_request_count`. `_fetch_one` creates a per-call
   `call_attempts` list and passes it through; error handlers read `call_attempts[0]`.
   No shared counter contamination under concurrency.

4. **Non-blocking #4 — duplicate manifests carry attempt_count**
   (`pipelines/ingest_sec_companyfacts.py:457-458`)
   Added `manifest.attempt_count = attempt_count` in the `skipped_duplicate` branch.

5. **Non-blocking #5 — concurrency max_workers assertion**
   (`tests/bronze/test_sec_companyfacts.py:1076-1157`)
   Monkey-patched `ThreadPoolExecutor` with a `TrackingThreadPool` that captures
   `max_workers`. Test asserts `all(mw <= 4 for mw in captured_max_workers)`.

## Additional tests added

- `test_error_message_does_not_leak_ua_value` — mutation-proof for Blocking #1
- `test_concurrent_attempt_count_per_cik` — two concurrent fetches (one retrying,
  one direct) each get their own attempt count (2 and 1 respectively)

## Checks run

- `python3 -m pytest tests/bronze/test_sec_companyfacts.py tests/rag/test_sec_rag_ingest.py -q` → **257 passed**
- Mutation "put repr(user_agent) back" → `test_error_message_does_not_leak_ua_value` **FAILED** (UA value leaked)
- Mutation "move seen_payloads.add before write" → `test_first_write_failure_allows_second_write` **FAILED** (fetched_count == 0)
- `test_concurrent_attempt_count_per_cik` → **PASSED** (TK0: 2 attempts, TK1: 1 attempt)

## Commits

- `7a700bf` fix(xbrl): remove user_agent value from validation error message
- `c2ab7aa` fix(xbrl): make seen_payloads mutation test exercise sequential ordering
- `da0ba3d` fix(xbrl): per-call attempt_count from fetch, carry count on duplicate manifests
- `721353f` test(xbrl): assert max_workers <= 4 in concurrency test
- `33f7b0f` test(xbrl): add mutation-proof test for UA error message not leaking input
- `ac92627` fix(xbrl): true per-call attempt tracking via _attempts parameter
- `eb7dcd4` test(xbrl): verify per-call attempt_count under concurrency
===VERDICT END===