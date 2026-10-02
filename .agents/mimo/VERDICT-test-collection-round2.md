# VERDICT: test-collection-round2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
None.

## Non-blocking notes
- `etl/extract_yfinance.py` still fails to import due to missing `etl/bulk_load_massive.py` (pre-existing; not related to db.database import changes). 5 of 6 ETL modules import cleanly; `extract_yfinance` needs `bulk_load_massive.py` restored or its import refactored separately.
- The 12 sentiment failures remain (dictionary file arrives with PR #8). No action taken per BUILD-REQUEST.

## Checks run
- `python3 -c "import etl.extract_polygon, etl.extract_options, etl.extract_edgar, etl.extract_cot, etl.extract_stocks"` → pass (5/6; extract_yfinance blocked by unrelated missing bulk_load_massive.py)
- `python3 -m pytest --co -q` → 371 tests collected, 0 collection errors (was 340)
- `python3 -m pytest -q -m 'not spark and not lakebase and not databricks'` → 12 failed, 289 passed, 67 skipped, 16 deselected in 3.93s (was 12 failed, 272 passed, 56 skipped)

## Changes made

### ETL modules (6 files)
Moved `from db.database import get_connection` from module top-level into a lazy `_get_connection()` helper that raises `RuntimeError("DuckDB local store was retired; production ingestion writes Delta via notebooks/01_ingest_market_data.py")` if the import fails. Pure helpers (`_ms_to_iso`, `_polygon_ticker`, `_to_int`, `_nested`, `_fetch_one`, etc.) are now importable without DuckDB.

| File | Functions using `_get_connection()` |
|---|---|
| `etl/extract_polygon.py` | `run_polygon_bars_etl`, `run_polygon_snapshots_etl`, `run_polygon_options_etl`, `run_polygon_reference_etl`, `run_polygon_option_bars_etl` |
| `etl/extract_options.py` | `refresh_option_chains`, `run_option_etl` |
| `etl/extract_edgar.py` | `run_edgar_filings_etl`, `run_edgar_facts_etl`, `run_edgar_13f_etl` |
| `etl/extract_cot.py` | `run_cot_etl` |
| `etl/extract_yfinance.py` | `run_yf_bars_etl`, `run_yf_indices_etl` |
| `etl/extract_stocks.py` | `run_stock_etl` |

### Test files (4 files)

| File | Before | After | Newly running tests |
|---|---|---|---|
| `tests/rag/test_persona_rails.py` | 0 collected (module-level skip) | 18 collected; 14 pass, 4 skipped | `check_persona_fit`, `_has_financial_figure` tests |
| `tests/test_extract_cot.py` | 0 collected (module-level skip) | 4 collected; 1 pass, 3 skipped | `test_to_int` |
| `tests/bronze/test_bronze_polygon_bars.py` | 0 collected (module-level skip) | 9 collected; 2 pass, 7 skipped | `test_polygon_bars_ms_to_iso_conversion`, `test_polygon_bars_ms_to_iso_none` |
| `tests/test_extract_polygon_ticks.py` | 0 collected (module-level skip) | 0 collected (unchanged) | Reason corrected: "removed; not carried forward" |

### Before/after summary
- **Collected:** 340 → 371 (+31)
- **Passed:** 272 → 289 (+17)
- **Skipped:** 56 → 67 (targeted per-test skips replace module-level skips)
- **Failed:** 12 → 12 (unchanged; all sentiment dict)