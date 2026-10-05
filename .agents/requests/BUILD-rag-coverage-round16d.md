# BUILD-rag-coverage round 16d — IMPLEMENT NOW (one order-dependent failure; small)

You are MiMo. Commit as you go, LF endings, do not touch `.agents/dispatch.sh`, never weaken tests.
Claude (WSL): `python3 -m pytest -q tests/rag tests/bronze` on this branch → 1 failed, 1126 passed (stable, 3 runs):
`tests/bronze/test_refresh_bronze_options.py::test_shape_day_emits_uppercase_right` — AssertionError inside
`pyspark/sql/connect/functions/builtin.py:138 _invoke_function` (`assert isinstance(arg, (Column, Expression))`): a CLASSIC pyspark Column
reached the Spark CONNECT functions module. The bronze test passes alone (37 passed) and the same command on origin/main passes (892 passed), so
a test or fixture ADDED ON THIS BRANCH leaves pyspark in Connect mode (e.g. sets `SPARK_CONNECT_MODE_ENABLED`/`SPARK_REMOTE`, imports
`databricks.connect`/`DatabricksSession`, or swaps `pyspark.sql.functions` in sys.modules) without restoring it.
Find it by bisecting the branch's new test files (`git diff --name-only origin/main...HEAD -- tests/`) run before the bronze test, fix the leak
at its source with proper teardown (monkeypatch.setenv/delenv, fixture finalizers, restoring sys.modules entries), and extend
tests/rag/test_zz_isolation.py to also assert pyspark is not left in Connect mode (env vars and `pyspark.sql.functions` identity).
Acceptance: `python3 -m pytest -q tests/rag tests/bronze` → 0 failed. Verdict: .agents/mimo/VERDICT-rag-coverage-round16d.md.
