# BUILD rag-kg round 7 (builder: MiMo; checker: Claude Sonnet subagent standing in for DeepSeek)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Commit after each stage. NEVER delete or weaken existing tests.
Checker verdict: .agents/deepseek/VERDICT-rag-kg-round6.md (CHANGES_REQUESTED). Production code is correct; the tests don't prove it.

## Item 1 (blocking): real pipeline tests
`TestPipelineValidation` in tests/rag/test_sec_knowledge_graph.py only imports `sec_kg.build.validate_and_raise`.
Replace or extend it with tests that IMPORT `pipelines.build_sec_knowledge_graph` and call its build entry point
(`build()` / `main()`, whichever performs the writes) with a FAKE Spark session plus a write spy (records every
createDataFrame / saveAsTable / write / sql CREATE/INSERT/MERGE call). Must work with pyspark absent (use the existing
fake_pyspark fixture pattern).
- (a) An undocumented rejection reason → `ValueError` raised AND the write spy records ZERO write/create calls.
- (b) Only documented reasons → writes happen, and they happen AFTER validation (assert order: validation recorded before the first write).
- (c) The manifest row written to `gold_sec_kg_build_runs` carries the exact expected counts (assert exact values).
Acceptance (mutation proofs you must run in /tmp copies and report):
- Replace the `validate_and_raise(...)` call at pipelines/build_sec_knowledge_graph.py:~103 with a plain dict → at least one test FAILS.
- Move the call after the table writes → at least one test FAILS.

## Item 2: explicit manifest schema
The manifest is written via `createDataFrame([Row(...)])`, which infers bigint / map<string,bigint>; the table DDL is INT / MAP<STRING,INT>.
Use an explicit StructType matching docs/DATA_SCHEMAS.md exactly, and add a test asserting the schema passed to createDataFrame matches the 9 documented columns and types.

## Acceptance commands
- python -m pytest tests/rag -q (all pass)
- pyspark hidden: PYTHONPATH=<nps shim> python -m pytest tests/rag -q (all pass)
Write .agents/mimo/VERDICT-rag-kg-round7.md with the mutation-proof outputs. Commit everything.
