# BUILD rag-coverage round 8a-2 (builder: MiMo) — finish round 8a

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-coverage. Commit after each item, descriptive messages.
NEVER delete or weaken existing tests. DeepSeek verdict: .agents/deepseek/VERDICT-rag-coverage-round8a.md (3 blocking). Do NOT start round 8b items.

1. Inserted count (pipelines/sec_rag_ingest.py:1577): report actual inserted ROWS. Use the Delta MERGE result (`spark.sql(MERGE ...)` returns a
   DataFrame with num_inserted_rows on Databricks — read it) or DeltaTable history `operationMetrics.numTargetRowsInserted` on the TARGET table
   (not the temp view). Delete the dead `DESCRIBE HISTORY _merge_src` block. Make FakeDataWriter mirror production semantics (MERGE: re-run inserts
   0). Tests: 50-chunk filing → rows_appended 50; re-run → 0.
2. Resume/attempt in production: implement a concrete `SparkIngestLogReader` (read_succeeded_accessions, read_max_attempt) over sec_ingest_log with
   pushed-down predicates (run_id / ticker), and construct it in `main()` so the guards at :1240/:1264 are live. Tests: main() wiring test asserts
   the reader is passed; fake-Spark reader test; resume skips succeeded; attempt = max + 1.
3. Make three tests fail on the OLD code (prove each by reverting the fix in a /tmp copy and pasting output):
   - test_history_overlap_uses_filing_to (:1594): fixture with filingFrom >= start_date (a history file entirely after start_date) that the old
     `filingFrom < start_date` logic skipped.
   - test_missing_acceptance_datetime_not_dropped (:1631): acceptanceDateTime array SHORTER than the forms array (the old min() truncation).
   - test_stale_cache_used_on_network_failure (:1671): include a `.meta` sidecar with an old timestamp so the old `ttl=0` path rejected it.
Acceptance: python3 -m pytest tests/rag tests/bronze -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-coverage-round8a2.md with counts + mutation outputs. Commit everything.
