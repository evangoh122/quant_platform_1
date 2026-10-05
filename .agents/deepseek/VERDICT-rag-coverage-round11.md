===VERDICT START===
# VERDICT: rag-coverage round 11 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 11

## Summary

The single Codex P1 from `.agents/codex/VERDICT-rag-coverage-r3.md` ("missing MERGE metrics silently reported
as zero") is fixed. Both writers now return `None` + `WARNING` for empty history, missing metrics key/map, and
exceptions, while a real reported `"0"` stays `0` and `"7"` stays `7`. `None` propagates through the build-level
aggregate (`rows_written` becomes `None`, never a partial sum or `0`). Every downstream consumer of the now-Optional
count is None-safe. The 12 new tests are behavioural, pass on HEAD, and are killed by the two required mutations in
`/tmp` copies (red phase confirmed at the test-only commit `0798921`).

## Verification

### 1. Both writers return None + WARNING; "0"→0; "7"→7

- `pipelines/sec_rag_ingest.py:1709` `inserted: Optional[int] = None` (was `0`); empty-history WARNING at
  `:1721-1725`, missing-key WARNING at `:1716-1720`, exception WARNING at `:1726-1730`. Exception path returns
  `None` (no `inserted = None` re-assignment needed, the initial `None` flows through). ✔
- `pipelines/build_sec_embeddings.py:285` `inserted: Optional[int] = None` (was `0`); same three WARNING branches at
  `:297-306`, `:292-296`, `:302-306`. ✔
- Covered by `tests/rag/test_merge_metrics.py`: `TestEmbedWriteBatchMetrics::test_empty_history_returns_none`,
  `test_missing_key_returns_none`, `test_exception_returns_none`, `test_metrics_with_zero_returns_zero`,
  `test_metrics_with_seven_returns_seven`, and the mirror `TestSparkDataWriterMetrics::…` set. ✔

### 2. Aggregate: any None → total None; [0,0] → 0; no `or 0` coercion

- `pipelines/build_sec_embeddings.py:157-162` `_accumulate` sets `rows_unknown = True` on any `None` result and
  stops adding thereafter; `:206` returns `None if rows_unknown else rows_written`. ✔
- `:151-155` `_embed_batch` no longer contains the old `return result if result is not None else 0` coercion
  (removed in `e0ca919`). ✔
- Covered by `TestAggregateNonePropagation::test_mixed_with_none_returns_none` (`[3, None, 2] → None`) and
  `test_all_zero_returns_zero` (`[0, 0] → 0`). ✔

### 3. DOWNSTREAM None-safety (every consumer of the now-Optional count)

- `pipelines/sec_rag_ingest.py:1462` `log_entry.rows_appended = inserted` — field declared
  `rows_appended: Optional[int] = None` at `:242`. ✔
- Ingest log table write is None-safe: `SparkLogWriter.INGEST_LOG_SCHEMA` declares
  `StructField("rows_appended", IntegerType(), True)` (nullable) at `:1776`; `createDataFrame([row], schema=…)`
  at `:1812` uses the explicit schema (Spark accepts `None` in a nullable `IntegerType`); DDL
  `rows_appended INT` (no `NOT NULL`) at `:1832`. ✔
- No `+=` on `None`: both accumulation sites guard `if entry.rows_appended is not None:` at `:1496-1497`
  (threaded path) and `:1516-1517` (serial path). ✔
- Job summary `logger.info(... %d ...)` at `:1536` formats `result.total_rows_appended`, which is declared
  `int = 0` at `:1099` and only ever receives guarded `+=` — never `None`. ✔
- Embeddings job summary `print(f"\n  {result['rows_written']} rows written …")` at
  `build_sec_embeddings.py:353` renders `None` as the string `None` (no `TypeError`, no `:,` formatting). ✔
- No f-string `:,` formatting on `rows_written`/`rows_appended`/`total_rows_appended` anywhere (`rg -n ":,"`
  over both pipelines returns nothing). ✔
- Rollout idempotency gate (`docs/SEC_RAG_COVERAGE_RUNBOOK.md:165` "Expected: rows_written = 0") is a manual
  check over the printed result; with unknown metrics the value is now `None`, so the gate can no longer be
  falsely satisfied by a silent `0`. There is no code path that coerces `None` back to `0` before the gate. ✔

### 4. Tests are behavioural and the red phase is real

- New tests are behaviour-asserting (mock `DESCRIBE HISTORY` side-effects, assert return value **and** a
  `WARNING` with "unknown" in the message). ✔
- Red phase at test-only commit `0798921` (before the two fix commits): `pytest tests/rag/test_merge_metrics.py -q`
  → **5 failed** (`TestEmbedWriteBatchMetrics::test_empty_history_returns_none`,
  `test_missing_key_returns_none`, `TestSparkDataWriterMetrics::test_empty_history_returns_none`,
  `test_missing_key_returns_none`, `TestAggregateNonePropagation::test_mixed_with_none_returns_none`). The two
  exception tests were already green at red phase because the pre-existing `except` path already returned `None`
  (fix commit `66a730b` notes "Exception handler unchanged"). ✔
- Mutation A (re-init `inserted` to `0` in both writers, in `/tmp/qp1-mut1` copy): **7 failed** (all six
  `*_returns_none` tests plus the aggregate test, since batch-1 unknown became `0`). ✔
- Mutation B (restore `or 0` coercion in `_embed_batch`, in `/tmp/qp1-mut2` copy):
  `test_mixed_with_none_returns_none` → **FAILED** (`assert 5 is None`). ✔

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` → **664 passed, 36 skipped, 0 failed** (21.3s)
- `python3 -m pytest tests/rag/test_merge_metrics.py -q` → **12 passed**
- Red phase `git archive 0798921 | tar -x -C /tmp/qp1-red` → **5 failed** (named tests above)
- Mutation A (`/tmp/qp1-mut1`, `inserted: Optional[int] = 0`) → **7 failed**
- Mutation B (`/tmp/qp1-mut2`, restore `return result if result is not None else 0`) → **1 failed**
- `git diff --check 0798921^..HEAD` → clean (no whitespace errors)
- `git show --stat 0798921 66a730b e0ca919` → in-scope files only (`tests/rag/test_merge_metrics.py`,
  `pipelines/sec_rag_ingest.py`, `pipelines/build_sec_embeddings.py`)

## Non-blocking notes

- `SparkIngestLogReader.read_succeeded_accessions` (`sec_rag_ingest.py:1867-1872`) still interpolates `run_id`
  into a `WHERE` clause. Pre-existing, runbook-controlled, not user-facing input, and out of scope for this
  round (flagged previously; not a regression of this change).
- `total_rows_appended` remains `int` and silently omits unknown (None) entries from the summary total; the
  authoritative per-filing count is now correctly `None` in `rows_appended`, so the aggregate is conservative
  rather than falsely zero. Acceptable for this round; a future round may want an explicit "unknown" signal in
  the summary.
===VERDICT END===
