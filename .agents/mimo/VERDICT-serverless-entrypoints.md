# VERDICT: serverless-entrypoints — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
(none)

## Non-blocking notes
- `ml/run_ablation.py` was not touched — it has no `__file__` hacks and no direct Spark usage (imports from `ml.*` which are pure-Python/MLflow). Not in scope per the deepseek verdict.
- `lakebase_analytics.py:666` previously used `SparkSession.builder.getOrCreate()` directly. Now uses `get_spark()` from `_runtime`, which picks ambient session when `DATABRICKS_RUNTIME_VERSION` is set. Correct for serverless.
- `sec_rag_ingest.py` had 9 separate `DatabricksSession.builder.serverless(True)` call sites across 4 Spark adapter classes + 2 standalone functions + `main()`. All consolidated to `get_spark()` from `_runtime`, preserving the injectable `spark_factory` pattern for testability.
- `run_silver_gold.py:37` (`HERE` constant) now uses `str(repo_root())` instead of `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`. Equivalent path, no behavioral change.

## Checks run
- `python3 -m pytest tests/test_jobs_serverless.py -q` → 9 passed
- `python3 -m pytest tests/test_jobs_serverless.py tests/test_bundle_sync.py tests/test_app_yaml.py tests/test_requirements_completeness.py -q` → 17 passed
- `grep -rn 'DatabricksSession.builder.serverless' pipelines/ ml/ --include='*.py' | grep -v _runtime.py` → no matches (clean)
- `grep -rn '__file__' pipelines/ ml/ --include='*.py' | grep -v _runtime.py | grep -v __pycache__` → no matches (clean)
- `python3 -c 'from pipelines._runtime import get_spark, repo_root; print(repo_root())'` → `/home/jianj/code/qp1-main` (correct)

## Files created
- `pipelines/_runtime.py` — shared `repo_root()` and `get_spark()` helpers

## Files modified
- `pipelines/build_sec_embeddings.py` — replaced `_SCRIPT` + `DatabricksSession` with `_runtime` imports
- `pipelines/build_sec_knowledge_graph.py` — replaced `Path(__file__)` + `SparkSession.builder.getOrCreate()` with `_runtime`
- `pipelines/run_silver_gold.py` — replaced `__file__` + `DatabricksSession` with `_runtime`
- `pipelines/sec_rag_ingest.py` — replaced all 9 `DatabricksSession.builder.serverless()` calls + `Path(__file__)` with `_runtime`
- `pipelines/lakebase_analytics.py` — replaced `SparkSession.builder.getOrCreate()` with `get_spark()`
- `resources/jobs.yml` — removed `libraries: []` from `lakebase_analytics_refresh` serverless task

## Files created (tests)
- `tests/test_jobs_serverless.py` — 9 tests covering all acceptance criteria + 3 named mutation tests