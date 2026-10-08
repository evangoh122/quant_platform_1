===VERDICT START===
# VERDICT: xbrl-B1a-r2 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 2

## Summary

Reviewed round 2 commit `80c5c38` on `feat/xbrl-fundamentals` against
`BUILD-xbrl-B1a-r2.md` and my round-1 `CHANGES_REQUESTED` verdict. Both blocking
items are now fixed and mutation-proven; the non-blocking bounded-concurrency item
is implemented. All four named mutations fail as required, the same-payload skip
test is real (removing the skip logic fails a test), and the offline suite is green.

## Blocking findings

None.

## Item-by-item

- **Item 1 (four named mutations) — PASS.** Re-verified independently in fresh
  `git archive HEAD` copies under `/tmp` (see table below). The round-1 blocker —
  "overwrite instead of append" caught by no test — is now caught by
  `TestSparkWriterAppendMode` (4 tests failing on the mutation). All four fail.
- **Item 2 (same-payload skip test real) — PASS.** `test_same_payload_skipped_within_run`
  (`tests/bronze/test_sec_companyfacts.py:637`) is a real test now: two tickers map
  to CIK `0000320193`, both fetch identical payloads, and it asserts
  `fetched_count == 1`, `skipped_duplicate_payloads == 1`, `len(delta_rows)` equals
  exactly one fetch's rows (rows written once), and the manifest carries one
  `success` + one `skipped_duplicate` entry with the matching `payload_hash`.
  Removing the skip logic (`if (cik, payload_hash) in seen_payloads:` → `if False:`)
  → **1 failed** (`assert 2 == 1` at `:689`).
- **Item 3 (bounded concurrency + attempt_count) — PASS (non-blocking).**
  `ThreadPoolExecutor(max_workers=min(4, len(ticker_cik_pairs)))`
  (`pipelines/ingest_sec_companyfacts.py:429,533`) caps workers at 4 and shares the
  process-wide `get_global_limiter` singleton (`:366`). Shared `seen_payloads` and the
  `result` counters are guarded by a single `threading.Lock` (`:428`). Manifest
  `attempt_count` is the real delta of `client.request_count` around each fetch
  (`:442,446,475`), and `test_attempt_count_from_retries` proves it (429 + retry →
  `attempt_count == 2`). `test_rate_limiter_holds_with_concurrency` asserts
  `limiter.max_rps <= 10`.
- **Item 4 (offline suite) — PASS.** `python3 -m pytest -q -m "not spark and not
  lakebase and not databricks"` → **2477 passed, 107 skipped, 24 deselected** (274 s).

## Mutation verification (independent `git archive HEAD` copies under /tmp)

| Mutation | Applied to | Result |
|---|---|---|
| accept placeholder UA (`if _placeholder_re.search(ua_lower):` → `if False:`, sec_rag_ingest.py:172) | /tmp/mut1_placeholder_ua | **3 failed** (test_reject_placeholder_email, test_reject_your_email_placeholder, test_mutation_accept_placeholder_ua) |
| remove rate limiter (`self._limiter.acquire()` → `pass`, sec_rag_ingest.py:821) | /tmp/mut2_remove_limiter | **1 failed** (test_rate_cap_respected: `assert 1000.0 > 1000.0`) |
| overwrite instead of append (`mode("append")` → `mode("overwrite")`, ingest_sec_companyfacts.py:630,692) | /tmp/mut3_overwrite | **4 failed** (test_facts_writer_uses_append_mode, test_manifest_writer_uses_append_mode, test_facts_writer_no_overwrite, test_manifest_writer_no_overwrite) |
| drop malformed facts (`return rows` → filter `value_decimal is not None`) | /tmp/mut4_drop_malformed | **2 failed** (test_flatten_malformed_value_decimal_is_none, test_mutation_malformed_fact_not_dropped) |
| remove same-payload skip (`if (cik, payload_hash) in seen_payloads:` → `if False:`, ingest_sec_companyfacts.py:452) | /tmp/mut5_remove_skip | **1 failed** (test_same_payload_skipped_within_run: `assert 2 == 1`) |

## Non-blocking notes

- **[tests/bronze/test_sec_companyfacts.py:898]** `test_bounded_concurrency_max_workers`
  does not actually assert `max_workers <= 4`; it only asserts 6 tickers are fetched.
  The ≤4 cap is enforced in code (`ingest_sec_companyfacts.py:429`) but a mutation
  raising the cap would not fail this test. Recommend asserting the cap directly
  (e.g. patch `ThreadPoolExecutor` and inspect `max_workers`).
- **[pipelines/ingest_sec_companyfacts.py:451-458]** The `skipped_duplicate` manifest
  branch sets `fetch_status`/`completed_at` but never assigns the `attempt_count`
  computed at `:446`, so it keeps the dataclass default `1`. Correct for a clean
  single-request duplicate, but undercounts if the duplicate fetch hit a 429/5xx first.
- **[pipelines/sec_rag_ingest.py:822]** `SecClient._request_count += 1` is not
  atomic; the `request_count - req_before` delta used for `attempt_count` could
  theoretically undercount under concurrent fetches (≤4 threads). Pre-existing in
  `SecClient`, low probability under the ≤10 rps cap.
- **SQL injection review** (ROLE mandate): the only SQL strings are `CREATE TABLE
  IF NOT EXISTS` DDL with f-string `{catalog}.{schema}` identifiers (no WHERE filter,
  no interpolated values); writes use `df.write.mode("append").saveAsTable(...)`.
  No parameterized-query violation.

## Checks run

- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` → **42 passed** (0.10 s)
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **2477 passed, 107 skipped, 24 deselected** (274.22 s)
- mut1 → 3 failed; mut2 → 1 failed; mut3 → 4 failed; mut4 → 2 failed; mut5 → 1 failed
===VERDICT END===
