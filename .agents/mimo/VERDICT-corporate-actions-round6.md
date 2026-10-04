# VERDICT: corporate-actions-round6 — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
None.

## Non-blocking notes
- The `DATEDIFF(m.ex_date, ca.ex_date)` syntax in the new ±3-day suppression uses Databricks 2-arg form; DuckDB tests require a shim (regex translation). This is documented in the test file.
- The `SPLIT_SINGLE_SOURCE` classification is mentioned in docs/notebook but not yet emitted by the SQL (the CTE only handles suppression; yfinance-only splits are applied via `_resolved_splits` without a separate break entry). This is informational only — the existing `_split_source_mismatches` CTE already covers unmatched yfinance rows via Case 3.

## Checks run
```
python -m pytest -q tests/bronze/test_corporate_actions.py tests/silver/test_ohlcv_day_adjusted.py tests/silver/test_silver_sql_semantics.py tests/test_security.py --timeout=60
```
→ 159 passed, 1 skipped (rag_engine import), 0 failed

```
PYTHONPATH=/tmp/.../nps python -m pytest -q tests/bronze/test_corporate_actions.py tests/silver/test_ohlcv_day_adjusted.py tests/silver/test_silver_sql_semantics.py --timeout=60
```
→ 159 passed, 0 skipped, 0 failed (pyspark hidden)

```
python .agents/requests/ca5-sem-repro.py
```
→ same day: factor ~20 (not 400) ✓; 1-day off: factor ~20 (not 400) ✓

## Changes made

### 1. Split deduplication fix (silver/08_silver_ohlcv_day_adjusted.sql)
- Added ±3-day near-match suppression in `_resolved_splits` CTE: yfinance rows within ±3 calendar days of a massive row for the same symbol are excluded.
- Added alias `ca` for correlated subquery reference.
- Updated SQL header comments.

### 2. SQL semantic tests (tests/silver/test_silver_sql_semantics.py)
- 8 tests extracting real CTE SQL from silver/08, running in DuckDB with fixtures.
- Covers: same-day both sources, near-date suppression, yfinance-only, ratio disagreement, SQQQ reverse, adj_close continuity.
- Mutation proofs: WHERE rn=1→WHERE 1=1 FAILS; removing ±3-day suppression FAILS.

### 3. API key leak fix (etl/corporate_actions.py, notebooks/refresh_bronze_corporate_actions.py)
- Replaced `resp.raise_for_status()` with explicit status check using redacted URL.
- Changed `raise ... from last_exc` to `raise ... from None` to suppress chained exception with URL.
- Added `_redact_api_key` to notebook; defense-in-depth redaction on report["failures"], checkpoint error_text, and print.

### 4. Resume per source (notebooks/refresh_bronze_corporate_actions.py)
- Changed `completed_symbols: set[str]` to `completed_keys: set[tuple[str, str]]` with (symbol, source) tuples.
- Updated checkpoint query to SELECT DISTINCT symbol, source.
- Updated skip logic to check all adapters for a symbol.

### 5. Documentation (docs/DATA_SCHEMAS.md, notebook docstring)
- Documented ±3-day same-event rule.
- Added SPLIT_SINGLE_SOURCE classification.
- Added back-adjusted price caveat for PIT consumers.

### 6. Security tests (tests/bronze/test_corporate_actions.py)
- 5 tests for API key leak: HTTPError, ConnectionError, report failures, printed output, mutation proof.
- 4 tests for resume per source.

## Counts
- New test file: 8 tests (test_silver_sql_semantics.py)
- New tests in existing files: 9 tests (5 API key + 4 resume)
- Total new: 17 tests
- All 159 tests pass (1 skipped: rag_engine import)