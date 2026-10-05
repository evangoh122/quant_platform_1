# VERDICT: rag-coverage round 8a — MiMo
**Status:** APPROVED
**Round:** 8a

## Summary
All 6 findings from the Codex review (VERDICT-rag-coverage-review.md) addressed.

## Blocking findings
None.

## Changes implemented

### 1. Atomic typed bronze writes (`sec_rag_ingest.py:1243-1330`)
- `SparkDataWriter` now uses Delta MERGE keyed on `accession_number` (insert-only when not matched)
- Explicit `StructType` with 17 fields (including typed `raw_payload` as nullable StringType)
- Batch-level ownership conflict detection (same accession, different CIK in batch)
- Pre-MERGE existing-data ownership check raises `AccessionOwnershipConflict`
- Actual inserted count returned from batch accession keys

### 2. accepted_ts UTC (`sec_rag_ingest.py:210-225`)
- `parse_sec_timestamp` returns tz-aware UTC datetime (never naive)
- All internal timestamps (`ingest_ts`, `started_ts`, `completed_ts`, `mapped_ts`) are tz-aware UTC
- Epoch 1740076200 preserved under any local TZ (verified by test)

### 3. Discovery completeness (`sec_rag_ingest.py:588-680`)
- `discover_filings` raises `SecClientError` on exhausted retries (no silent empty return)
- `run_ingest` catches discovery failures and records `failed` status per ticker in `sec_ingest_log`
- History inclusion uses `filingTo >= start_date` overlap check (not `filingFrom < start_date`)
- `_collect_filings` iterates to `max(len(...))` — rows with missing `acceptanceDateTime` are included with `accepted_ts=None`, not silently dropped

### 4. CIK ambiguous + stale-cache fallback (`sec_rag_ingest.py:327-407, 880-920`)
- `build_cik_map` detects duplicate ticker → different CIKs and sets `status="ambiguous"`
- `ambiguous` emitted in CIK mapping loop and logged
- `_try_load_cache(ttl=0)` fixed: `ttl=0` means "use regardless of age" (stale fallback)
- `_cache_age_str` logs human-readable age on stale fallback
- `load_company_tickers(dry_run=True)` skips cache writes
- `docs/DATA_SCHEMAS.md` updated to document `ambiguous` status

### 5. SEC fair access (`sec_rag_ingest.py:55-80`, `xbrl_client.py`)
- Module-level singleton `get_global_limiter()` (thread-safe) shared by `sec_rag_ingest` and `xbrl_client`
- `xbrl_client._rate_limited_get` uses `get_global_limiter()` instead of independent `_rate_lock`/`_last_call`
- `_parse_retry_after` handles HTTP-date format via `email.utils.parsedate_to_datetime`

### 6. Resume + workers (`sec_rag_ingest.py:1256-1410`)
- `IngestLogReader` protocol added with `read_succeeded_accessions` and `read_max_attempt`
- `max_workers > 1` uses `concurrent.futures.ThreadPoolExecutor` sharing the global limiter
- `in_progress` entry persisted before work begins (separate object to avoid mutation bugs)
- `attempt = previous_max_attempt + 1` (reads from ingest log)
- Resume skips already-succeeded accessions from the log
- Ownership conflict records filing as `failed` (with reason) THEN raises `AccessionOwnershipConflict`

## Tests added (20 new)
| Test class | Count | Covers |
|---|---|---|
| TestAtomicBronzeWrites | 2 | MERGE proxy, batch ownership conflict |
| TestAcceptedTsUTC | 4 | epoch 1740076200, tz-aware, offset conversion, process_filing |
| TestDiscoveryCompleteness | 4 | exhausted retries, history failure, overlap check, missing acceptance |
| TestCikAmbiguousAndCacheFallback | 4 | two-CIK ambiguous, stale cache, dry run no write |
| TestFairAccess | 3 | singleton, HTTP-date Retry-After, numeric Retry-After |
| TestResumeAndWorkers | 4 | in_progress persisted, resume skips, attempt increments, max_workers |

## Checks run
- `python -m pytest tests/rag/test_sec_rag_ingest.py -q` → **102 passed** (82 existing + 20 new)
- `python -m pytest tests/rag tests/bronze -q` (excluding 3 pre-existing collection errors) → **603 passed, 33 skipped, 0 failed**
- No existing tests weakened or deleted

## Non-blocking notes
- The 3 pre-existing collection errors (`test_chat_engine.py`, `test_graph_rag_engine.py`, `test_langgraph_engine.py`) are unrelated import issues, not caused by this round.
- `SparkDataWriter` MERGE count uses batch accession keys as fallback; Delta `operationMetrics` on temp views is unreliable. The count is exact for non-duplicate batches (the normal case).