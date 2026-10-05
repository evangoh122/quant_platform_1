# BUILD rag-coverage round 10 (builder: MiMo) — production blockers from Codex review 2

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-coverage. Commit after each item, descriptive messages. NEVER delete or weaken tests.
Codex review: .agents/codex/VERDICT-rag-coverage-review2.md (4×P1, 1×P2). Each fix needs a test that FAILS on the old code — prove it in a copy made with
`git archive HEAD | tar -x -C /tmp/<dir>` and paste outputs. Fake Spark must REJECT schema-less rows with all-None columns the way real PySpark does
(raise like CANNOT_DETERMINE_TYPE) so this class of bug is caught in tests.

1 (P1). pipelines/sec_rag_ingest.py:1737 SparkLogWriter infers schema from one row with completed_ts/error_code/error_message None → CANNOT_DETERMINE_TYPE in
   production before any filing is fetched. Use an explicit StructType for sec_ingest_log matching docs/DATA_SCHEMAS.md. Audit EVERY createDataFrame in the
   lane (bronze rows, CIK mapping log, embeddings, coverage) for schema inference with nullable all-None columns; give each an explicit schema.
2 (P1). Cold start: main always wires SparkIngestLogReader and :1323 queries sec_ingest_log before the first write; no DDL exists. Add an
   ensure-table step (CREATE TABLE IF NOT EXISTS with the documented schema) run at startup, and make the reader return "no prior attempts" on a fresh
   table. Fix the runbook name (SEC_RAG_COVERAGE_RUNBOOK.md:174 says bronze_sec_ingest_log). Test: fresh environment (table absent) → ingest starts.
3 (P1). Pre-existing accession ownership conflicts (:1283 anti-join path) raise before an audit row is written. Record a failed sec_ingest_log entry
   (error_code ownership_conflict) THEN raise/continue per policy. Test: zero → one audit row.
4 (P1). silver/05_silver_sec_sections.sql:20 and 06_silver_sec_entities.sql:22 hard-code bootcamp_students.evangoh_capstone; use the same
   catalog/schema placeholders the runner substitutes (and make the runner substitute them). Test: rendered SQL for the prod target references
   evangoh_capstone_prod everywhere; grep test for any remaining hard-coded schema in silver/05,06, gold/07 and pipelines/.
5 (P2). When DESCRIBE HISTORY / MERGE metrics are unavailable, do NOT fall back to len(rows) (bronze :1694, embeddings :280): report the count as
   unknown (None) and log a WARNING; never a candidate count. Missing metrics must not silently report 0 either. Tests.
Acceptance: python3 -m pytest tests/rag tests/bronze -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-coverage-round10.md. Commit everything.
