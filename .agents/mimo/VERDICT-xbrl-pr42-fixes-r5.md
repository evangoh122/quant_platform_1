# VERDICT: xbrl-pr42-fixes-r5 — MiMo
**Status:** APPROVED
**Round:** 5

## Blocking findings
(none)

## Non-blocking notes
- All four serverless contract tests fixed in a single focused commit
- `pyyaml>=6.0` already present in `environments[].spec.dependencies`; removing the task-level `libraries:` entry was the minimal correct fix
- Both SparkCompanyFactsWriter and SparkCompanyFactsManifestWriter now use `_runtime.get_spark()` as fallback while preserving `spark_factory` injection for tests
- The `_p = globals().get("__file__") or sys.argv[0]` bootstrap pattern matches all other entry points (run_silver_gold.py, build_sec_embeddings.py, sec_rag_ingest.py, etc.)

## Checks run
- `python3 -m pytest -q tests/test_jobs_serverless.py` → 16 passed (0.16s)
- `python3 -m pytest -q tests/bronze/test_sec_companyfacts.py` → 94 passed (10.93s)
- `git diff --check` → clean (no trailing whitespace)

## Failing-before evidence
Pre-fix archive (`/tmp/r5-proofs/pre-fix`):
- `test_no_libraries_on_serverless_tasks` → FAIL (task has libraries key)
- `test_no_bare_dunder_file_in_entry_points` → FAIL (line 33: bare `__file__`)
- `test_no_serverless_session_outside_runtime` → FAIL (line 758: DatabricksSession.builder.serverless)
- `test_no_databricks_connect_import_outside_runtime` → FAIL (lines 757, 801: databricks.connect import)

## Mutation proofs
All run from `/tmp/r5-proofs/mutation_proofs.py` against working tree:

1. **Proof 1** — Reintroduce task-level `libraries:` → `test_no_libraries_on_serverless_tasks` FAIL ✓
2. **Proof 2** — Reintroduce bare `__file__` → `test_no_bare_dunder_file_in_entry_points` FAIL ✓
3. **Proof 3a** — Reintroduce `from databricks.connect import DatabricksSession` → `test_no_databricks_connect_import_outside_runtime` FAIL ✓
4. **Proof 3b** — Reintroduce `DatabricksSession.builder.serverless()` call → `test_no_serverless_session_outside_runtime` FAIL ✓
5. **Proof 4** — Bypass `spark_factory` in SparkCompanyFactsWriter → `test_facts_writer_uses_append_mode` FAIL ✓
6. **Proof 5** — Round-4 deterministic-worker tests (max_workers, zero_raises, bounded_concurrency, concurrent_duplicate_reservation, first_write_failure) → all PASS ✓

## Commit
`d746b06` on `feat/xbrl-fundamentals` — `fix(serverless): remove task-level libraries and use _runtime helpers`