===VERDICT START===
# VERDICT: xbrl-B1a-r7r8 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 7+8

The r7/r8 runtime fixes are real (explicit StructType passed to `createDataFrame`,
`http_status` added to the manifest, idempotent `ALTER`, cache min-entry guard, `/Volumes`
fallback), and 5 of the 6 requested mutations are caught by tests. But the core r7
acceptance criterion "remove `http_status` from the DDL → test fails" is **not** met:
the manifest/bronze DDL and the StructType are two independent hardcoded column lists
with no test linking them, so the `DELTA_METADATA_MISMATCH` class of bug is not guarded.

## Blocking findings

- [pipelines/ingest_sec_companyfacts.py:786-803] (`SparkCompanyFactsManifestWriter.ensure_table` DDL)
  and [pipelines/ingest_sec_companyfacts.py:108-136] (`_get_manifest_schema`) are **not a single
  source of truth** — the DDL column list and the StructType are duplicated by hand and no test
  asserts they stay equal. The same is true for the bronze DDL
  [pipelines/ingest_sec_companyfacts.py:717-748] vs `_get_bronze_schema` [:65-105].
  → Mutation: remove `fact_count INT` from the manifest DDL (a column with **no** `ALTER`
  backstop) → the entire offline suite still passes (81+203). In production the 14-field
  DataFrame would then be appended to a 13-field table → `DELTA_METADATA_MISMATCH`, the exact
  live-run failure r7 was meant to eliminate, with zero offline coverage.

- [pipelines/ingest_sec_companyfacts.py:796] removing `http_status INT` from the manifest DDL
  alone (the literal r7 mutation "remove http_status from the DDL → test fails") does **not** fail
  any test: `TestManifestSchemaContract` compares the StructType against a third hardcoded list in
  the test, never against the actual DDL string; `TestEnsureTableIdempotent` only counts
  `ALTER` calls. Only the `http_status` case is incidentally backstopped by the `ALTER` logic —
  every other column divergence (e.g. `fact_count`, `payload_bytes`) is silently unguarded.

## Specified mutations (each must fail a test)

1. Drop `schema=` from both `createDataFrame` calls → `TestCreateDataFrameAlwaysWithSchema`
   **3 failed** (`test_bronze_writer_passes_schema`, `test_manifest_writer_passes_schema`,
   `test_mutation_remove_schema_arg_fails`).
2. Remove `http_status` from manifest **StructType** → `TestManifestSchemaContract` **5 failed**.
   Remove `http_status` from manifest **DDL only** → **0 failed** (BLOCKING — see above).
3. `ALTER TABLE` issued unconditionally (revert r8 bug-1 fix) →
   `test_ensure_table_skips_alter_when_http_status_exists` **1 failed**.
4. Remove the `tests/bronze/conftest.py` autouse cache fixture → mtime of
   `/tmp/sec_cache/company_tickers.json` unchanged **before and after** the 284-test run
   (with the fixture: unchanged; without the fixture: also unchanged). No current test touches
   the real cache path either way — the fixture is defense-in-depth, not load-bearing.
5. Accept a cache with <1000 entries (revert r8 bug-2b guard) → `TestCacheMinEntries` **2 failed**.
6. Remove the `/Volumes` fallback → `TestCachePathFallback::test_fallback_when_volumes_not_writable`
   **1 failed**.

## Earlier B1a mutations re-run (all still caught)

- r6 m1 (clean): drop `status_code` from retry-exhausted `SecClientError` → `test_retry_exhaustion_{403,429,503}_manifest` **3 failed**.
- r6 m2: `_classify_error` → constant `client_error` → **4 failed**.
- r6 m3: remove 403 retry → `test_mutation_403_not_retried` **1 failed**.
- r6 m4: neutralize UA validation → `test_mutation_accept_placeholder_ua` **1 failed**.
- r6 m5: drop success `manifest.http_status` → `test_manifest_http_status_on_success` **1 failed**.
- r6 m6: mark payload seen before write → `test_first_write_failure_allows_second_write` **1 failed**.
- r6 m7: shared request-counter attempt calc → `test_concurrent_attempt_count_per_cik` **1 failed**.
- r5 m2: drop duplicate `manifest.attempt_count` → `test_duplicate_manifest_attempt_count_with_retries` **1 failed**.
- r5 m3: re-leak UA in error message → `test_error_message_does_not_leak_ua_value` **1 failed**.
- r5 m5: `max_workers` 4→16 → `test_bounded_concurrency_max_workers` **1 failed**.

(Note: the committed r6 `deepseek-CHECK-xbrl-B1a-r6-mutate.sh m1` full-file revert now fails for a
spurious reason — it restores `sec_rag_ingest.py@80f607a~1` which lacks the r8 `is_fallback`
parameter, so tests raise `TypeError: unexpected keyword 'is_fallback'` rather than the intended
`status_code` assertion. Verified separately with a point mutation above.)

## Non-blocking notes

- [pipelines/ingest_sec_companyfacts.py:174-188] `MANIFEST_COLUMNS` is missing `logged_at`
  (13 entries vs the 14-column DDL/StructType) and is dead code; `BRONZE_FACT_COLUMNS` [:145-171]
  is also unused. Recommend deleting both or deriving the DDL + StructType from one list.
- [pipelines/sec_rag_ingest.py:1431-1435] `run_sec_rag_ingest` still defaults `cache_path` to
  `/Volumes/...` with no fallback, so the same "Permission denied: '/Volumes'" warning persists in
  that pipeline (out of scope for this slice, but the same class of bug).
- [tests/bronze/conftest.py:4] unused `from unittest.mock import patch` import; file lacks a
  trailing newline.
- The autouse cache fixture patches `tempfile.gettempdir` globally but does not clear
  `SEC_COMPANY_TICKERS_CACHE`, so a test running with that env var set would bypass the isolation.

## Checks run

- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` → **81 passed**
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q` → **203 passed**
- Offline suite total → **284 passed** (baseline, `6c99f60`, working tree clean)
- Mutations (r7/r8 + earlier) in `/tmp/qp1-r7r8-mutate` / `/tmp/qp1-r5-mutate` / `/tmp/qp1-r6-mutate`
  copies via `git archive HEAD | tar -x` → results tabulated above; **m2-DDL and m2c (fact_count)
  are the two that do NOT fail**.
===VERDICT END===
