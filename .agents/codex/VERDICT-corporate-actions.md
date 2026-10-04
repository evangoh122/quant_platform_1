===CODEX VERDICT START===

# CHANGES_REQUESTED

Checker gate: `VERDICT-corporate-actions-check3.md` says **APPROVED**.

## Blocking findings

1. The adjusted-Silver MERGE violates the required explicit-column contract.

   [silver/08_silver_ohlcv_day_adjusted.sql:364](/home/jianj/code/qp1-corpact/silver/08_silver_ohlcv_day_adjusted.sql:364) uses `WHEN NOT MATCHED THEN INSERT *`. Every MERGE INSERT must list every target column exactly once. Existing tests only enforce this for `data_quality_breaks`, as shown at [test_ohlcv_day_adjusted.py:691](/home/jianj/code/qp1-corpact/tests/silver/test_ohlcv_day_adjusted.py:691).

2. The notebook is not reliably usable as a Databricks NOTEBOOK or notebook JOB.

   - [refresh_bronze_corporate_actions.py:143](/home/jianj/code/qp1-corpact/notebooks/refresh_bronze_corporate_actions.py:143) calls strict `parse_args()` on injected kernel arguments. Direct proof with `-f /tmp/kernel.json` exited with status 2 before Spark.
   - [refresh_bronze_corporate_actions.py:152](/home/jianj/code/qp1-corpact/notebooks/refresh_bronze_corporate_actions.py:152) attempts `import dbutils` and sets it to `None` on failure, instead of retaining Databricks’ injected `dbutils` global. Consequently, widget/job parameters at [lines 182–218](/home/jianj/code/qp1-corpact/notebooks/refresh_bronze_corporate_actions.py:182) may never be read.

   Minimal fix: capture `globals().get("dbutils")`; when that injected object exists, parse an empty argv and obtain notebook/job parameters from widgets. Otherwise retain strict `parse_args()` for script/CLI execution. Add tests for injected `-f kernel.json`, injected `dbutils`, notebook widgets, and normal strict CLI rejection.

## Verification

- Required full command stalled without producing output for over one minute and was stopped; no full-suite pass is claimed.
- Focused corporate-action suite: **91 passed**.
- Adjustment proof:
  - AMZN adjusted return: **+1.994%**
  - Reverse split and forward-plus-reverse multiplication: correct
  - Volume adjustment: inverse to price
  - Dollar volume: invariant
- PIT:
  - `adj_*` is documented as global/current-scale and returns-only at [silver SQL lines 11–15](/home/jianj/code/qp1-corpact/silver/08_silver_ohlcv_day_adjusted.sql:11).
  - Split availability is 09:30 New York at [corporate_actions.py:69](/home/jianj/code/qp1-corpact/etl/corporate_actions.py:69).
  - Independent results: `2022-06-06 20:30Z`, `2022-12-05 21:30Z` for 16:30 closes.
- Breaks:
  - ≥40% threshold: [SQL lines 196–226](/home/jianj/code/qp1-corpact/silver/08_silver_ohlcv_day_adjusted.sql:196).
  - META fixture is flagged and masked: [test lines 405–417](/home/jianj/code/qp1-corpact/tests/silver/test_ohlcv_day_adjusted.py:405).
  - Masked returns become `NULL`, not zero: [SQL lines 338–348](/home/jianj/code/qp1-corpact/silver/08_silver_ohlcv_day_adjusted.sql:338).
  - Reviewed allow-list decisions are preserved: [SQL lines 282–295](/home/jianj/code/qp1-corpact/silver/08_silver_ohlcv_day_adjusted.sql:282).
- Bronze references use only valid `bronze_ohlcv_day` columns.
- CLI correctly rejects abbreviations/unknown flags, parses before Spark, sets `sys.path`, and defaults to dry-run.

===CODEX VERDICT END===
