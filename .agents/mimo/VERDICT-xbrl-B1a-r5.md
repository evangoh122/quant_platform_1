===VERDICT START===
# VERDICT: xbrl-B1a-r5 — MiMo (builder)
**Status:** APPROVED
**Round:** 5

## Blocking findings

None.

## Non-blocking notes

- BarrierFakeHttpClient added to test infrastructure: URL-routed, thread-safe
  (deque + lock), optional one-shot `threading.Barrier` for forcing genuine
  thread overlap. `barrier_urls` restricts which URLs participate so
  `load_company_tickers` (main thread, different URL) does not deadlock.
- `test_concurrent_attempt_count_per_cik` rewritten: uses Barrier + URL-routed
  responses so CIK A (429→200) and CIK B (200) genuinely overlap. Shared-counter
  mutation (`client.request_count - req_before`) yields `assert 3 == 2` on TK0.
- `test_duplicate_manifest_attempt_count_with_retries` added: two tickers map to
  same CIK, second fetch gets 429→200 (2 attempts), skipped_duplicate manifest
  must record `attempt_count=2`. Mutation (`drop manifest.attempt_count =
  attempt_count` from skipped_duplicate branch) yields `assert 1 == 2`.
- No production code changed. Only test file modified.

## Checks run

- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` → **55 passed**
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **2493 passed, 107 skipped, 24 deselected** (227s)
- Mutation "faithful revert to shared `client.request_count` deltas" (c2ab7aa pipeline state) → **1 FAILED** (`assert 3 == 2`)
- Mutation "drop `manifest.attempt_count` on skipped_duplicate branch" → **1 FAILED** (`assert 1 == 2`)
- Commit: `07b2a87` on `feat/xbrl-fundamentals`
===VERDICT END===