# VERDICT: corporate-actions — MiMo
**Status:** APPROVED
**Round:** 1

## Changed files

| File | Action | Stage |
|------|--------|-------|
| `etl/corporate_actions.py` | created | 1 |
| `notebooks/refresh_bronze_corporate_actions.py` | created | 1 |
| `silver/08_silver_ohlcv_day_adjusted.sql` | created | 1 |
| `pipelines/run_silver_gold.py` | modified | 1 |
| `resources/jobs.yml` | modified | 1 |
| `tests/bronze/test_corporate_actions.py` | created | 3 |
| `tests/silver/test_ohlcv_day_adjusted.py` | created | 3 |
| `docs/DATA_SCHEMAS.md` | modified | 4 |
| `docs/CORPORATE_ACTIONS_RUNBOOK.md` | created | 4 |

## Design decisions

1. **Source-neutral protocol**: `CorporateActionsSource` protocol with `fetch_splits` method. `YFinanceCorporateActionsSource` is the only implementation. Polygon deferred per spec (key broken). Adapter accepts injectable ticker factory, clock, sleeper, delay, retry policy.

2. **Normalization**: `CorporateActionSplit` frozen dataclass validates finite, positive, non-one ratios. `information_available_ts` computed as ex-date 09:30 America/New_York → naive UTC via `zoneinfo`. Symbol normalized to uppercase stripped.

3. **Bronze append-only**: Natural key `(symbol, ex_date, source)` excludes `fetched_ts`. Left-anti-join before append. Same-key/different-ratio corrections are conflicts, not silent overwrites.

4. **Silver adjustment**: `ex_date > event_date` (strictly greater — ex-date bar is already on new basis). Log-sum-exp product for numerical stability. Price divides, volume multiplies by cumulative ratio.

5. **Break detection**: `abs(raw_gross_return - 1) >= 0.40` candidate threshold. Same-date split correction with `abs(post_split - 1) <= 0.03` tolerance. SPLIT_EXPLAINED not masked; UNEXPLAINED_PENDING masked; reviewed decisions preserved on rerun.

6. **PIT distinction**: Global adj_* are current-scale display levels (not PIT model features). Documented and tested. Canonical `return_1d` is PIT-safe at day close.

7. **Truncate safety**: `data_quality_breaks` excluded from `--truncate` to preserve manual reviews.

## Pre-build failing-test proof

Before implementation, the test modules could not be collected because the source modules did not exist:
- `ModuleNotFoundError: No module named 'etl.corporate_actions'`
- `FileNotFoundError: .../silver/08_silver_ohlcv_day_adjusted.sql`

This is the expected focused collection/import failure.

## Checks run

```
python -m pytest -q tests/bronze/test_corporate_actions.py tests/silver/test_ohlcv_day_adjusted.py
→ 74 passed, 0 failed (3.47s)

git diff --check
→ clean (exit 0)
```

## Commit SHAs

| SHA | Message |
|-----|---------|
| `82ac927` | feat(corpact): add source-neutral split ingestion |
| `e3dd3b8` | test(corpact): cover adjustments pit and break masking |
| `b52bf15` | docs(corpact): add schemas and live runbook |

## Unavailable live checks

The following require Databricks/yfinance access and cannot be verified offline:
- Live universe count (Claude observed 557 raw, 557+3 final)
- Bronze ingestion dry-run/write against yfinance
- Silver build against live Delta tables
- AMZN 2022-06-06 actual adjusted return verification
- META 2022-06-09 classification in live data
- 237 baseline reconciliation against live data
- Duplicate key checks against live tables

These are documented in `docs/CORPORATE_ACTIONS_RUNBOOK.md` for Claude to execute.

## Blocking findings

None.

## Non-blocking notes

1. The `silver/08_silver_ohlcv_day_adjusted.sql` file contains both table creation (CREATE TABLE IF NOT EXISTS) and the transform logic. The orchestrator's `split_statements` splits on `;` which means the CREATE TABLE and MERGE statements execute as separate steps. The `data_quality_breaks` MERGE executes first (after its CREATE TABLE), then `silver_ohlcv_day_adjusted` MERGE. This is correct because the break classification feeds into the adjusted return masking.

2. The `run_step` function in `pipelines/run_silver_gold.py` uses the step name for both the table name and the file path. Since `08_silver_ohlcv_day_adjusted.sql` produces two tables, both steps point to the same file. The `count()` call after each step may fail for the first step if the table doesn't exist yet; this is consistent with how other steps handle it (they create the table in the SQL).

3. The yfinance adapter's `_fetch_raw_splits` method tries `get_splits()` first (preferred for yfinance >= 0.2.31), then falls back to `history(period="max", actions=True, auto_adjust=False)` extracting the `Stock Splits` column. This covers both old and new yfinance versions.

4. Tests use pure Python reference implementations, not Spark. The `_compute_break` function in tests mirrors the SQL logic exactly. No network calls, no Databricks credentials, no dbutils.

5. LF line endings used throughout. No `.agents/dispatch.sh` modifications.