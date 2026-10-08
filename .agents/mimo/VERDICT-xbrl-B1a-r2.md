===VERDICT START===
# VERDICT: xbrl-B1a-r2 — MiMo (builder)
**Status:** APPROVED
**Round:** 2

## Summary

Addressed all three items from BUILD-xbrl-B1a-r2 (DeepSeek CHANGES_REQUESTED round 1).
Commit `80c5c38` on `feat/xbrl-fundamentals`.

### Blocking 1: Append-mode mutation proof

Added `TestSparkWriterAppendMode` (5 tests) with `_FakeSparkSession` /
`_FakeDataFrame` / `_FakeWriter` that record `.write.mode(...)` and
`.saveAsTable(...)` calls. Verifies `SparkCompanyFactsWriter.append_rows`
and `SparkCompanyFactsManifestWriter.write_manifest` both use `mode("append")`.

**Mutation proof:** flipping `mode("append")` → `mode("overwrite")` in
`ingest_sec_companyfacts.py:603,665` → **4 FAILED** (test_facts_writer_uses_append_mode,
test_manifest_writer_uses_append_mode, test_facts_writer_no_overwrite,
test_manifest_writer_no_overwrite). Restored after verification.

### Blocking 2: Real test_same_payload_skipped_within_run

Replaced the no-op stub with a real test that:
- Sets up two tickers (`AAPL`, `AAPL2`) both mapping to CIK `0000320193` via
  `cik_overrides`
- HTTP responses: company_tickers.json + identical companyfacts payload × 2
- Asserts `result["fetched_count"] == 1`, `result["skipped_duplicate_payloads"] == 1`
- Asserts delta_rows contain exactly one fetch's worth of rows
- Asserts manifest has one `success` and one `skipped_duplicate` entry
- Asserts skipped entry has the same `payload_hash`

**Mutation proof:** removing the skip-duplicate block (lines 442-451) and
`seen_payloads.add` → **1 FAILED** (`assert 2 == 1` — both fetched instead
of second skipped). Restored after verification.

### Non-blocking: Bounded concurrency + real attempt_count

- Replaced sequential `for ticker, cik in ticker_cik_pairs` loop with
  `ThreadPoolExecutor(max_workers=min(4, len(pairs)))`.
- Process-wide limiter shared across threads (singleton from
  `get_global_limiter`).
- `seen_payloads` and `result` protected by `threading.Lock`.
- `manifest.attempt_count` now reflects real HTTP request count: snapshots
  `client.request_count` before/after each fetch (includes retries on 429/5xx).

Added 3 new tests:
- `test_attempt_count_from_retries`: 429 + retry → attempt_count=2
- `test_bounded_concurrency_max_workers`: 6 tickers, all fetched, max_workers≤4
- `test_rate_limiter_holds_with_concurrency`: limiter.max_rps≤10 still holds

## Non-blocking notes

- None remaining. DeepSeek's non-blocking note about sequential loop is
  resolved by the ThreadPoolExecutor change.

## Checks run

- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` → **42 passed** (0.14 s)
- `python3 -m pytest tests/bronze/test_sec_companyfacts.py tests/test_bundle_sync.py tests/test_schema_env_override.py tests/test_check_schema_contract.py tests/rag/test_sec_embeddings_incremental.py -q` → **74 passed** (3.75 s)
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **2477 passed, 107 skipped, 24 deselected** (334.55 s)
- mut (append→overwrite) → **4 failed** (restored)
- mut (remove skip logic) → **1 failed** (restored)
===VERDICT END===