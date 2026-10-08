# BUILD: PR #42 fixes round 2 (checker CHANGES_REQUESTED — schema contract tests skip in CI)

You are MiMo. Branch `feat/xbrl-fundamentals` (stay on it). Read `.agents/deepseek-fallback/VERDICT-xbrl-pr42-fixes.md`. LF endings, never touch `.agents/dispatch.sh`, no Databricks,
no network. Shell rule as before (`.agentlogs/<name>.sh` + `wsl -d Ubuntu -- bash <path>`; no PowerShell, nothing in C:\temp). Stage only files you change. COMMIT; verdict
`.agents/mimo/VERDICT-xbrl-pr42-fixes-r2.md`. Tests may only call production code; never copy its logic.
tests/bronze/test_sec_companyfacts.py:1788,1942 — the bronze and manifest schema/DDL contract classes skip without PySpark, so CI (no PySpark) never checks the contract (33 skipped).
The schema is now plain-Python `_ColumnSpec`s and the DDL is generated from them — test THAT without PySpark: generated DDL column names/order/SQL types/NOT NULL == the _ColumnSpec list,
for both tables; ALTER-missing-columns derives from the same specs. Keep ONLY the tests that genuinely need a real StructType behind the PySpark skip (and make that skip list minimal).
Prove it: run the bronze tests with pyspark and databricks.connect imports blocked (sys.meta_path finder that raises ModuleNotFoundError) — the contract tests must RUN and pass, and the
skipped count must drop by at least 30. Mutation: drop a column from the DDL generator → a test fails WITHOUT PySpark.
