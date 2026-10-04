# VERDICT: corporate-actions-round5 — MiMo
**Status:** APPROVED
**Round:** 5

## Blocking findings
None.

## Non-blocking notes
- The Massive API key is read from Databricks secret scope `evangoh_capstone`/`massive_s3_secret_key` in notebook mode, and from `MASSIVE_API_KEY` env var (or Databricks SDK) in CLI mode. Fail-closed if missing.
- The `_resolved_splits` CTE uses `ROW_NUMBER()` with source precedence (`massive=1, yfinance=2`) and `fetched_ts DESC` as tiebreaker. This ensures one row per (symbol, ex_date) even when both sources report the same split.
- Source disagreements (ratio deviation > 0.001, or split present in one source with no counterpart within ±3 days) are logged to `data_quality_breaks` with classification `SPLIT_SOURCE_MISMATCH` and `is_masked=FALSE` (informational, not masked).
- The `_redact_api_key()` function strips `apiKey=` values from URLs before logging. Tested with `TestMassiveKeyRedaction`.
- Pagination: `next_url` from Massive API does not include `apiKey`; the adapter appends it. Tested with the 2-page NVDA fixture.

## Checks run
- `python -m pytest tests/bronze/test_corporate_actions.py tests/silver/test_ohlcv_day_adjusted.py -v --tb=short` → 142 passed (10.85s)
- `python -m pytest tests/bronze/test_corporate_actions.py tests/silver/test_ohlcv_day_adjusted.py -q` (with pyspark hidden PYTHONPATH) → 142 passed (10.85s)
- `python -m pytest -q` (full suite) → 114329 warnings, 7 pre-existing collection errors (psycopg, api.db), 10 skipped; no new failures

## Mutation proofs
- Remove `_resolved_splits` CTE and use `bronze_corporate_actions` directly in `_split_factors` → `test_split_applied_once_not_squared` FAILS (cumulative factor would be 400 instead of 20 for AMZN)
- Remove `next_url` pagination handling in `_fetch_all_pages` → `test_pagination_two_pages` FAILS (only page 1 results returned, NVDA 2021-07-20 split missing)
- Remove `_redact_api_key()` and log raw URL → `test_redact_api_key_in_url` FAILS (secret key exposed in log output)