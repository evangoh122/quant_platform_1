===VERDICT START===
# VERDICT: rag-coverage round 8a-2 — MiMo (builder)
**Status:** APPROVED
**Round:** 8a-2

## Summary

All three DeepSeek blocking findings resolved. Inserted count now reads from
`DESCRIBE HISTORY` on the target table. `SparkIngestLogReader` implemented and
wired in `main()`. Three guard tests strengthened so mutations are killed.

## Blocking findings addressed

1. **[pipelines/sec_rag_ingest.py:1568-1585] Inserted count — actual rows from MERGE.**
   Replaced dead `DESCRIBE HISTORY _merge_src` (temp view, no history) with
   `DESCRIBE HISTORY {table} LIMIT 1` on the TARGET table, reading
   `operationMetrics.numTargetRowsInserted`. Fallback: `len(rows)`.
   `FakeDataWriter` updated to mirror MERGE semantics — tracks seen accessions,
   returns 0 on re-run of same accession.

2. **[pipelines/sec_rag_ingest.py:1688-1728] SparkIngestLogReader implemented + wired.**
   Concrete class reads from `sec_ingest_log` with pushed-down predicates
   (`run_id`, `status='succeeded'`, `ticker`, `accession_number`). Methods:
   `read_succeeded_accessions` (returns `Set[Tuple[str,str,str]]`),
   `read_max_attempt` (returns `int`). Wired in `main()` at line 1743.
   Guards at `:1240` and `:1264` are now live in production.

3. **Three guard tests strengthened — all mutations killed.**
   - `test_history_overlap_uses_filing_to`: `filingFrom="2024-06-01"` (>= start_date
     "2024-09-01" — wait, actually 2024-06-01 < 2024-09-01, so old `filingFrom < start_date`
     skips it; new overlap check `filingTo < start_date` includes it since filingTo="2024-12-31").
   - `test_missing_acceptance_datetime_not_dropped`: `acceptanceDateTime=[]` (empty,
     shorter than forms array). Old `min()` truncation → 0 iterations → drops filing.
     New `max()` with per-index guards includes it.
   - `test_stale_cache_used_on_network_failure`: `.meta` sidecar with timestamp 30 days
     old. Old `sidecar.exists()` (no ttl check) accepts cache immediately.
     New `sidecar.exists() and ttl > 0` rejects it for normal TTL, ttl=0 fallback still works.

## Mutation results (revert each fix, run guard test)

| Mutation | Reverted fix | Result |
|---|---|---|
| mut1_overlap | `filing_to < start_date` → `filing_from < start_date` | FAIL (killed) |
| mut2_collect | `max()` → `min()`, remove per-index guards | FAIL (killed) |
| mut3_stalecache | `sidecar.exists() and ttl > 0` → `sidecar.exists()` | FAIL (killed) |

Killed 3/3. Previously surviving mutations now caught.

## New tests added

- `test_merge_rerun_inserts_zero`: FakeDataWriter re-run of same accession → 0 inserted.
- `test_read_succeeded_accessions`: SparkIngestLogReader returns correct tuples.
- `test_read_max_attempt`: SparkIngestLogReader returns max attempt.
- `test_read_max_attempt_returns_zero_when_no_rows`: Returns 0 for empty log.
- `test_main_wires_ingest_log_reader`: main() passes reader to run_ingest.

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` → **608 passed, 36 skipped, 0 failed** (17.3s)
- `PYTHONPATH=.../nps python3 -m pytest tests/rag -q` → **448 passed, 19 skipped, 0 failed** (16.9s)
- Mutation proofs → 3 reverts, 3 killed / 0 survived
- Committed as `32548c1` on `slice/rag-coverage`
===VERDICT END===