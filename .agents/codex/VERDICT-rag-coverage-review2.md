===VERDICT START===

# VERDICT: rag-coverage-r2 — Codex

Status: CHANGES_REQUESTED

DeepSeek round-9 approval was present. The repository remained unmodified.

## Findings

1. **[P1] The production ingest-log writer cannot persist normal `in_progress` rows.** [sec_rag_ingest.py:1737](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1737) relies on schema inference for a single row whose `completed_ts`, `error_code`, and `error_message` are all `None`. PySpark infers these as unresolved `NullType` fields and raises `CANNOT_DETERMINE_TYPE`. Because the write occurs before the processing `try` at [sec_rag_ingest.py:1368](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1368), production filings fail before fetching or writing bronze data. An explicit log `StructType` is required.

2. **[P1] Resume cannot cold-start on a clean deployment.** Main always wires `SparkIngestLogReader`, and [sec_rag_ingest.py:1323](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1323) queries `sec_ingest_log` before the first `in_progress` write. The reader query at [sec_rag_ingest.py:1763](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1763) has no table-not-found handling, and the repository contains no DDL or ensure-table path for this table. The runbook further directs operators to a different name, `bronze_sec_ingest_log`, at [SEC_RAG_COVERAGE_RUNBOOK.md:174](/home/jianj/code/qp1-ragcov/docs/SEC_RAG_COVERAGE_RUNBOOK.md:174).

3. **[P1] Pre-existing accession ownership conflicts still are not recorded.** The initial anti-join raises directly at [sec_rag_ingest.py:1283](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1283), before constructing or appending a failed log entry. An independent probe produced zero `ownership_conflict` audit rows. Only the later race-path conflict is logged.

4. **[P1] The downstream SEC transforms ignore the configured target schema.** [05_silver_sec_sections.sql:20](/home/jianj/code/qp1-ragcov/silver/05_silver_sec_sections.sql:20) and [06_silver_sec_entities.sql:22](/home/jianj/code/qp1-ragcov/silver/06_silver_sec_entities.sql:22) still hard-code `bootcamp_students.evangoh_capstone`. The bundle’s production target selects `evangoh_capstone_prod`, so ingestion and coverage use the configured schema while both silver transforms read and write development tables.

5. **[P2] MERGE metrics can still revert to candidate counts.** If `DESCRIBE HISTORY` fails, bronze returns `len(rows)` at [sec_rag_ingest.py:1694](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1694), and embeddings do the same at [build_sec_embeddings.py:280](/home/jianj/code/qp1-ragcov/pipelines/build_sec_embeddings.py:280). On an idempotent or raced MERGE this is not the actual inserted count. Missing history metrics also silently report zero.

## Verification

- `python3 -m pytest tests/rag tests/bronze -q`: **643 passed, 36 skipped**.
- Independent global 429 cooldown probe: passed; the peer worker remained blocked until the shared deadline.
- Independent bronze concurrency probe: passed; four calls used serialized MERGEs, retained every batch, and returned their own metrics.
- Spark schema-inference probe: detected unresolved `NullType` fields in the real ingest-log row.
- Ownership-conflict audit probe: failed with zero required audit rows.
- `git diff --check origin/main...HEAD`: passed.
- Worktree remained clean.
- Environment-only limitation: local `SparkSession` creation was unavailable because the installed PySpark is Databricks Connect remote-only; the underlying PySpark inference path was inspected and exercised directly.

## Independent mutations

All mutations used `git archive HEAD` copies under `/tmp`; all were killed:

1. Replaced UUID bronze views with fixed `_merge_src`: concurrency regression test failed.
2. Removed `SecClient`’s global cooldown trigger: peer worker bypassed the 429 deadline and the custom probe failed.
3. Allowed missing `accepted_ts` through PIT filtering: missing-timestamp exclusion test failed.

Mutation score: **3/3 killed**.

===VERDICT END===
