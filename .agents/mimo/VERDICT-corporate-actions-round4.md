# VERDICT: corporate-actions-round4 — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
None.

## Non-blocking notes
- The `notebook_task` in jobs.yml uses `base_parameters` which injects widget values; the notebook declares widgets with defaults first, then reads overrides. This is the correct Databricks pattern.
- The `globals().get("dbutils")` pattern avoids the kernel-injected `-f kernel.json` argparse crash while preserving the existing CLI path.

## Checks run
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → 639 passed, 67 skipped
- `python3 -m pytest -q -p no:cacheprovider tests/bronze/ tests/silver/` → 286 passed, 12 skipped
- No pyspark imports in bronze/silver tests → verified via grep
- LF line endings on all modified files → verified via `grep -rPl '\r'`

## What was done
1. **silver/08_silver_ohlcv_day_adjusted.sql**: Replaced `UPDATE SET *` and `INSERT *` with explicit column lists (24 columns each) in the silver_ohlcv_day_adjusted MERGE.
2. **tests/silver/test_ohlcv_day_adjusted.py**: Added `test_no_merge_uses_insert_star` (global INSERT */UPDATE SET * ban), `test_silver_adjusted_merge_insert_has_explicit_columns`, `test_silver_adjusted_insert_covers_all_target_columns` (DDL-driven column coverage), and `test_silver_adjusted_missing_column_would_fail_test` (proves detection works).
3. **notebooks/refresh_bronze_corporate_actions.py**: Rewrote `main()` for dual mode — notebook path uses `globals().get("dbutils")`, declares widgets with defaults, reads from widgets, ignores sys.argv; CLI path uses strict argparse. Spark init after parameter resolution in both paths.
4. **tests/bronze/test_corporate_actions.py**: Added `TestNotebookMode` class (6 tests): kernel argv + fake dbutils → widgets, widget mode=write, widget mode=bogus → error, no dbutils + --bogus → exit nonzero, no dbutils + --help → exit 0, globals pattern assertion. Updated `test_notebook_import_no_side_effects` to verify `globals().get("dbutils")`.
5. **resources/jobs.yml**: Switched `corporate_action_refresh` from `spark_python_task` with CLI parameters to `notebook_task` with `base_parameters`.