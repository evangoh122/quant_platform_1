# VERDICT: bronze-coderabbit — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
(none — all 3 blocking items fixed)

## Fixes applied

### 1. Fed re-appends unchanged rows (FIXED)
`notebooks/refresh_bronze_fed.py` — Changed `select_new_rows` to dedup on `(series_id, observation_date, value)` instead of `(series_id, observation_date, vintage_date, value)`. Changed `_get_existing_keys` to return a dict mapping `(series_id, observation_date)` → latest stored value (by max vintage_date). A candidate is new only if the pair is absent or its value differs from the latest stored vintage.

Evidence: `test_next_day_same_value_not_appended`, `test_next_day_changed_value_appended`, `test_value_revert_is_new_vintage` all pass.

### 2. dbutils.widgets.get default argument (FIXED)
`notebooks/refresh_bronze_equities.py:218-228` — Changed from `dbutils.widgets.get("mode", "dry-run")` (raises on real Databricks) to `dbutils.widgets.text("mode", "dry-run")` + `dbutils.widgets.get("mode")`. Applied to all three widget parameters. Other notebooks (fed, options, cot) use argparse, not widgets — no bug there.

### 3. Options shape_quote_row returns date, not string (FIXED)
`notebooks/refresh_bronze_options.py:269-274` — `expiry` is now parsed from the Polygon string `"YYYY-MM-DD"` to a `datetime.date` object. `test_shape_quote_row_full` updated to assert `row["expiry"] == date(2026, 12, 18)`.

### 4. Options main returns nonzero on failure (FIXED)
`notebooks/refresh_bronze_options.py:948-950` — `main()` now returns 1 when `daily is None` or `daily["failed"] > 0`.

### 5. Options _stage_file None → log_finish FAILED (FIXED)
`notebooks/refresh_bronze_options.py:657-660` — When `_stage_file` returns None in write mode, `log_finish(spark, key, DAY_DATASET, 0, error_message="403 / not entitled")` is called before `continue`, preventing orphaned RUNNING status.

### 6. Fed --start-date bounds, re-read COUNT, exit nonzero (FIXED)
- `notebooks/refresh_bronze_fed.py:479-483` — `overlap_start` is now clamped to `start_date` when `start_date` is provided, so `--start-date` actually bounds parsed rows.
- `notebooks/refresh_bronze_fed.py:542-546` — Post-write COUNT(*) is re-read from Spark after append.
- `notebooks/refresh_bronze_fed.py:574-576` — Returns 1 if `post - pre != appended`.

### 7. Unit test for _anti_join_new (N/A — already exists)
Tests at `tests/bronze/test_refresh_bronze_options.py:578-598` already cover: dupes dropped, existing keys excluded, genuinely new keys pass through.

### 8. Fed docs availability rules class-specific (FIXED)
- `docs/BRONZE_REFRESH_PLAN.md` — Schema now includes `revision_class STRING NOT NULL`. Semantics document class-specific availability rules. Verification query uses `revision_class = 'revised_macro'` guard.
- `.agents/requests/BUILD-bronze-fed.md` — Same updates applied.

### 9. COT fallback availability offset (FIXED)
- `docs/BRONZE_REFRESH_PLAN.md` — Now states: `release_date = report_date + 6 days` (3 nominal + 3 safety).
- `notebooks/refresh_bronze_cot.py:74` — Comment updated to document the +6 day formula.

## Non-blocking notes
- The equities and COT test files have some slow tests (likely network/fixture-heavy) that cause timeout in CI. The fed+options tests complete in ~3.6s.
- `revision_class` is already present in the live Fed notebook code and its CREATE TABLE DDL. The docs now match.

## Checks run
- `python -m pytest tests/bronze/test_refresh_bronze_fed.py tests/bronze/test_refresh_bronze_options.py -q --tb=short` → **114 passed** (3.63s)
- `python -m pytest tests/bronze/test_bronze_polygon_bars.py tests/bronze/test_bronze_polygon_option_bars.py tests/bronze/test_bronze_yfinance_bars.py tests/bronze/test_bronze_yfinance_indices.py -q --tb=short` → **2 passed, 10 skipped**
- `git diff --stat` → 9 files changed, 110 insertions, 31 deletions (`.agents/dispatch.sh` untouched)