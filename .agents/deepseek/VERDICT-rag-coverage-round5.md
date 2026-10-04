# VERDICT: RAG coverage round 5

Checker: Claude Sonnet subagent (DeepSeek out of credit)

Verdict: **CHANGES_REQUESTED** (items 1, 2, 4, 6, 7 pass; item 3 notebook delegation fails; items 2 and 5 have smaller gaps)

## Test runs (HEAD ab93003)
- `python3 -m pytest tests/rag tests/bronze -q` -> 569 passed, 29 skipped, **6 failed** (all `tests/bronze/test_refresh_bronze_cot.py::TestIdempotency`).
  These 6 also fail on base 4db30fa when run combined (566 passed, 6 failed), so it is cross-directory test pollution, not a round-5 regression.
  `tests/bronze` alone: 167 passed, 10 skipped at HEAD. Note the acceptance line "tests/rag tests/bronze all pass" is not met as a combined run.
- pyspark hidden (nps shim), `tests/rag`: 408 passed, 19 skipped.

## Findings
1. PASS - `test_three_tickers_parallel` (tests/rag/test_hybrid_retriever.py ~2799-2841) uses `Barrier(3, timeout=2)`.
   Mutation (/tmp/rc5-mut-1: hold `_inflight_lock` around `_load_ticker_corpus`, hybrid_retriever.py:358): test FAILS (AssertionError at :2838). Good.
2. PASS with a gap - `test_main_write_mode_writes_filings_and_log` (test_sec_rag_ingest.py ~1102-1175) uses fake adapters.
   Mutation (/tmp/rc5-mut-2: remove universe/accession/data/log kwargs, and separately the 4 + cik kwargs): test FAILS (:1169), other 68 pass. Good.
   Gap: it asserts only counts (`total_rows > 0`, `len(appended) == 2`, 2 succeeded entries with ticker NVDA). The request asked for "exact rows"; no row content/accession/chunk count is checked, and `main()` does not assert that the CIK mapping log writer received entries (it is a throwaway `FakeCikMappingLogWriter()`).
3. FAIL (notebook) - `notebooks/02_ingest_sec_edgar.py:72` only added a comment, "Delegate UA construction to pipelines/sec_rag_ingest.py". The notebook does NOT delegate: it still builds its own `HEADERS`/`User-Agent` at :80 and again at ~:1697-1707, and still has its own ingestion code. The comment is also misleading. Required: thin wrapper calling `pipelines.sec_rag_ingest`, no own UA string. (It does fail closed on `EDGAR_EMAIL`, so no placeholder remains, but the delegation requirement is unmet.)
   PASS - `notebooks/refresh_bronze_cot.py:70-80` `_build_cot_headers()` reads `CFTC_USER_EMAIL`, raises if missing or containing "example"; `download_year` (:114) uses it.
   PASS - `TestNoPlaceholderUserAgent` is a repo-wide `rglob` of `*.py` and `*.yml`, excluding tests/.agents/.git/__pycache__/archive. Mutation (/tmp/rc5-mut-3: append `contact@example.com` string to `api/services/embeddings.py`): scan FAILS. Passes at HEAD. (Nit: comment lines are exempt and an `archive` dir is excluded.)
4. PASS - `AccessionOwnershipConflict(ValueError)` at sec_rag_ingest.py:66; both raise sites (:1049, :1108) use it; only `except AccessionOwnershipConflict: raise` remains (:1170). `test_race_path_conflict_raises` exists (anti-join returns {} first, conflict on 2nd read). Mutation (/tmp/rc5-mut-4: remove the re-raise): race test FAILS, others pass.
5. PARTIAL - Implemented (not removed). `SparkCikMappingLogWriter` (sec_rag_ingest.py ~1290-1311), `CikMappingLogEntry`, wiring in `run_ingest` (~1014-1026) and `main()`. Columns and order match docs/DATA_SCHEMAS.md:495-502 (ticker, lookup_symbol, cik, status, reason, mapped_ts, run_id); no DDL file exists in the repo. `TestCikMappingLog` covers `run_ingest` with a fake writer (mapped + missing). Problems:
   - The Spark adapter is untested and uses `spark.createDataFrame([row])` with no explicit schema, one DataFrame and one `saveAsTable` per ticker. PySpark cannot infer a type from a single row where `cik`/`lookup_symbol` is None, which is exactly the "missing" case (cik=None, sec_rag_ingest.py ~:360). It will likely raise in production. Use an explicit StructType and write all entries in one batch. The unit test cannot catch this because it uses a fake.
   - Test does not check `cik`/`reason`/`mapped_ts` values.
6. PASS - build_sec_embeddings.py:128-129 comment now says `get_embeddings()` is a singleton shared by workers.
7. PASS - `git diff 4db30fa..HEAD -- tests`: only two removed assert lines, both in the old sleep-based three-ticker test (replaced by the barrier). Hardcoded 7-file grep test replaced by the wider scan; `test_different_cik_accession_raises_value_error` renamed and narrowed to the new exception. No tests deleted.

## Required for APPROVED
- Make the SEC notebook a real thin wrapper over `pipelines/sec_rag_ingest.py` (remove its own UA and ingestion code, or at minimum its own UA).
- Give `SparkCikMappingLogWriter` an explicit schema and batch write; add a test using the fake_pyspark fixture.
- Strengthen the main() write-mode test to assert row content and CIK mapping log entries.
- Fix or explain the combined `tests/rag tests/bronze` ordering failures (pre-existing).
