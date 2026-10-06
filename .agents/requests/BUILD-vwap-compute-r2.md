# BUILD-vwap-compute round 2 (luna CHANGES_REQUESTED — `.agents/deepseek-fallback/VERDICT-vwap-compute.md`)
You are MiMo. Branch `fix/vwap-compute`, worktree /home/jianj/code/qp1-vwap. Same shell rules as BUILD-vwap-compute.md (WSL direct, no PowerShell/C:\temp, stage only your files,
COMMIT, no Databricks access).
1. `silver/08_silver_ohlcv_day_adjusted.sql:82-84`: remove the unconditional `ALTER TABLE ... ADD COLUMNS (vwap_source STRING)`. Instead add `ensure_day_adjusted_columns(spark)` in
   pipelines/run_silver_gold.py modelled exactly on `ensure_model_availability_columns` (read existing columns, add only the missing `vwap_source STRING`, skip if table unreadable) and
   call it before the `silver_ohlcv_day_adjusted` step. Tests with a fake spark: column missing → one ALTER issued; column present → no ALTER; table unreadable → no ALTER, no raise.
   Also assert the SQL file contains no `ADD COLUMNS`. Mutation: always ALTER → the "present" test fails.
2. `tests/gold/test_gold_vwap_sql.py:56-69`: execute the REAL `vwap_deviation` expression from gold/01 (extract the feats SELECT or the full source query through the DuckDB shim) and
   assert its output; delete the Python re-computation. Mutation: change the SQL to `(close - vwap) / close` → test fails.
Run mutations in a /tmp `git archive` copy; run tests/gold tests/silver tests/pipelines (or wherever run_silver_gold tests live). Verdict `.agents/mimo/VERDICT-vwap-compute-r2.md`.
