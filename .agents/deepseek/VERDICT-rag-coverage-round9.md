===VERDICT START===
# VERDICT: rag-coverage round9 — DeepSeek
**Status:** APPROVED
**Round:** 9

## Blocking findings
(none)

## Non-blocking notes
- N1: `SparkDataWriter.append_bronze_rows` now uses a per-call uuid view name (`_merge_src_<hex12>`), a class-level `threading.Lock` (`SparkDataWriter._merge_lock`, shared across all instances), and reads the inserted count from `DESCRIBE HISTORY {table} LIMIT 1` **inside** the lock — so the metrics belong to that call's own MERGE, not another worker's. View dropped in `finally`. The concurrency test proves two threads get distinct view names and each reports its own count. No SQL injection: the interpolated identifiers are `catalog.schema.bronze_sec_filings_v2` and a uuid-hex view name (no user data).
- N2: `discover_filings` returns `(filings, failed_history_urls)`; `run_ingest` marks the ticker `partial` (error_code `history_fetch_failed`) in `sec_ingest_log` and surfaces `partial_count`/`partial_tickers` on `IngestResult` + the summary log line. Verified `accession_number="PARTIAL_COVERAGE"` cannot collide with resume (`read_succeeded_accessions` filters `status='succeeded'`, so a `partial` row is never treated as done). Note: `main()` still exits 0 on partial coverage (only `failed_count > 0` exits 1) — acceptable since the request allowed "failed **or partial** with reason".
- N3: `RateLimiter` gains `trigger_cooldown()` / `cooldown_remaining`; `acquire()` blocks all workers during cooldown (releases the lock while sleeping, re-checks at the top of the loop — no deadlock, verified against the non-reentrant `threading.Lock`). `MAX_RETRY_AFTER=120`; `Retry-After > cap` raises `SecClientError` (hard failure, no retry), which correctly propagates as ticker failure. Far-future HTTP-date `Retry-After` (2.3e9 s) is handled by the same cap path.
- N4: `_embed_and_write_batch` now returns the MERGE metric even when 0 (`return inserted`; `len(out_rows)` only as the DESCRIBE-HISTORY-failure fallback). Test proves 0 inserted → `rows_written == 0`.
- N5: `sys.path.insert(0, repo_root)` added to both entrypoints; `jobs.yml` declares `loguru`/`python-dotenv` (sec_embeddings) and `beautifulsoup4`/`lxml` (sec_rag_ingest). AST-based test enforces every top-level import is stdlib/repo-local/databricks-builtin/declared (BOM-stripped before parsing).
- Test-quality notes (not blocking): `test_one_worker_429_pauses_others` and `test_503_triggers_global_cooldown` don't actually assert the pause/cooldown side-effect strongly (they'd still pass if `acquire()` returned immediately); the assertion in `test_503...` is only a comment.
- Pre-existing (outside round-9 diff, not scored here): `SparkIngestLogReader.read_succeeded_accessions` / `read_max_attempt` still f-string-interpolate `run_id`/`ticker`/`accession_number` into SQL filters. These are internal identifiers (not user query params) and were not introduced in round 9, but worth a future parameterization pass per the "parameterized queries only" rule.

## Checks run
- `python3 -m pytest tests/rag tests/bronze -q` → **643 passed, 36 skipped, 0 failed** (was 629 passed before round 9; +14 new tests)
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` (pyspark hidden) → **483 passed, 19 skipped, 0 failed**
===VERDICT END===
