# BUILD corporate-actions round 5: Massive splits as primary source (builder: MiMo; checker: Claude Sonnet subagent)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/corporate-actions. Commit after each item.
NEVER delete or weaken existing tests. LF line endings.

Context (verified live by Claude 2026-10-04): Massive's REST API has splits.
`GET https://api.massive.com/v3/reference/splits?ticker=AMZN&limit=1000&apiKey=<key>` returns JSON
`{"status":"OK","results":[{"execution_date":"2022-06-06","split_from":1,"split_to":20,"ticker":"AMZN",...}],"next_url":...}`.
Observed: AMZN 2022-06-06 1→20; GOOGL 2022-07-18 1→20; TSLA 2022-08-25 1→3, 2020-08-31 1→5;
NVDA 2024-06-10 1→10, 2021-07-20 1→4; SQQQ reverse 2025-11-20 5→1 (and 7 earlier); META none.
The api key is Databricks secret scope `evangoh_capstone`, key `massive_s3_secret_key` (yes, the S3 secret key works as the REST apiKey).
NEVER hardcode, log, or put the key in an exception message or URL that gets logged — redact `apiKey=` in any logged URL.
You cannot reach Databricks or the internet; build against recorded fixtures. Claude runs the live check.

## 1. MassiveCorporateActionsSource (etl/corporate_actions.py)
- Implements `CorporateActionsSource.fetch_splits(symbol)`; `source="massive"`.
- split_ratio = split_to / split_from (AMZN 20.0, SQQQ 0.2). ex_date = execution_date.
  information_available_ts via the existing `information_available_ts_for`.
- Follow `next_url` pagination (append apiKey to next_url; it is not included). Retry with backoff on 429/5xx
  (bounded, configurable), raise on 401/403 with a message that does NOT contain the key.
- Filter results to exact `ticker == symbol` (defensive). Skip/record invalid ratios like the yfinance adapter does.
- Injectable HTTP session for tests. Fixtures in tests (JSON files) using the observed values above, incl. a 2-page pagination case.

## 2. Notebook / job wiring
- VALID_SOURCES = {"massive","yfinance"}; default source = "massive". Key read via `dbutils.secrets.get("evangoh_capstone","massive_s3_secret_key")`
  in notebook mode; in CLI mode via env var MASSIVE_API_KEY or the Databricks SDK WorkspaceClient secrets API. Fail closed if missing.
- `--source both` (widget too): fetch from both into bronze (the key is (symbol, ex_date, source), so rows coexist).

## 3. Silver must not double-apply splits (blocking correctness)
With two sources in bronze_corporate_actions, the LEFT JOIN in silver/08_silver_ohlcv_day_adjusted.sql (~L140) would
multiply each split twice. Add a resolved-splits CTE: one row per (symbol, ex_date), preferring source='massive',
falling back to 'yfinance' only for (symbol, ex_date) with no massive row. Use it everywhere splits are joined.
Disagreements → INSERT into data_quality_breaks (explicit columns) with a reason like 'split_source_mismatch':
same (symbol, ex_date) with |ratio_m/ratio_y - 1| > 0.001, OR a split present in one source with no counterpart in the
other within ±3 calendar days. Test: SQL-structure tests plus a pandas/DuckDB-or-equivalent semantic test showing a
split present in both sources is applied ONCE (cumulative factor 20, not 400).

## 4. Docs
docs/DATA_SCHEMAS.md + the notebook docstring: sources, precedence, mismatch reason codes.

## Acceptance
- python -m pytest -q (full) passes; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) passes.
- Mutation proofs in /tmp copies, report outputs: remove the source-precedence dedupe → the apply-once test FAILS;
  drop pagination → the 2-page test FAILS; log the raw URL → a key-redaction test FAILS.
- .agents/mimo/VERDICT-corporate-actions-round5.md. Commit everything.
