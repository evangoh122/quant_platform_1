Checker: Claude Sonnet subagent (DeepSeek out of credit)

# Verdict: CHANGES_REQUESTED  (round 6, 66237ed)

Tests: `python3 -m pytest tests/rag` = 390 passed, 19 skipped; with pyspark hidden = 390 passed, 19 skipped.
pandas-3 venv: not runnable (missing dotenv/duckdb/langchain_core; collection errors, environment only).

## Findings
1. BLOCKING - pipeline tests are vacuous. `TestPipelineValidation` (tests/rag/test_sec_knowledge_graph.py, section 22) imports only `sec_kg.build.validate_and_raise`; it never imports `pipelines.build_sec_knowledge_graph`, uses no fake Spark, no write spy. BUILD-round6 required "fake Spark: unknown reason -> no write calls (spy) + exception; known -> writes happen and manifest has exact counts". Not done. These tests duplicate TestValidateAndRaise.
   Mutation proof: /tmp/kg-mut-a replaced the pipeline's `validate_and_raise` call (pipelines/build_sec_knowledge_graph.py:103) with a plain dict -> 390 passed (survives). /tmp/kg-mut-b moved the call after the writes (before "Build complete") -> 390 passed (survives). Both must fail.
2. Code itself is correct on inspection: pipeline calls shared `validate_and_raise` at pipelines/build_sec_knowledge_graph.py:103, before any table create/write (schemas defined after, merges later); ValueError propagates uncaught from main() -> non-zero exit. Offline script uses the same function (scripts/build_sec_knowledge_graph.py ~line 143, exits 1). No duplicated logic (sec_kg/build.py:875). The problem is only that no test proves it.
3. Manifest: gold_sec_kg_build_runs written at pipeline lines ~216-250; DDL column names/types match docs/DATA_SCHEMAS.md (9 cols). Unverified (no Spark test): `createDataFrame([Row(...)])` infers map<string,bigint> / bigint for ints, while table is INT/MAP<STRING,INT>; `insertInto` after `.format("delta").mode("append")` relies on cast. Needs a test or explicit schema (StructType) on createDataFrame.
4. Neighbors timestamp: `test_neighbor_edge_timestamps_exact` is exact-value and non-vacuous. Mutation: +28800s on api/services/sec_knowledge_graph.py:576,579 -> that test fails (1 failed, 389 passed). OK. `test_neighbor_timestamp_mutation_detectable` is weak/redundant (no real mutation; it only asserts != a computed +8h), harmless.
5. No existing tests deleted/weakened: diff ed2bd81..66237ed -- tests is additions only (the one "-/+ assert len(stats.rejected) == 0" line is a no-newline-at-EOF change).
6. Other Codex findings: Codex's only other items were non-blocking/validated; the neighbor-timestamp gap is addressed (4). Exact stats emitted and logged only via the manifest table plus print of run_id; input/accepted/rejected counts are not printed (minor).

## Required for approval
Add tests that import pipelines.build_sec_knowledge_graph and run `build()` with a fake spark (spy on write/sql/createDataFrame): (a) unknown reason -> raises ValueError, zero write calls; (b) known reasons -> writes occur after validation and manifest row has exact counts. Both mutations in finding 1 must then fail. Consider explicit StructType for the manifest DataFrame.
