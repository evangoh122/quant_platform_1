# BUILD corporate-actions round 6 (builder: MiMo; checker: Claude Sonnet subagent; reviewer: dataexpert Claude)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/corporate-actions. Commit after each item with a
DESCRIPTIVE message (not "chore:"/"fix:" alone). NEVER delete or weaken existing tests. LF line endings.
Checker verdict: .agents/deepseek/VERDICT-corporate-actions-round5.md (CHANGES_REQUESTED). The checker's DuckDB repro of
bug 1 is at .agents/requests/ca5-sem-repro.py (read it).

## 1 (blocking). Split applied twice when sources disagree on ex_date
`_resolved_splits` (silver/08_silver_ohlcv_day_adjusted.sql ~133-160) dedupes only on exact (symbol, ex_date).
Massive AMZN 20:1 on 2022-06-06 + yfinance 20:1 on 2022-06-03 → cumulative factor 400 before 06-03. Must be 20.
New rule (per symbol):
- Every massive row is kept.
- A yfinance row is kept ONLY IF there is no massive row for the same symbol with |ex_date diff| <= 3 calendar days.
  (A near-match is the same corporate action; massive wins on both date and ratio.)
- Near-match pairs with a date difference > 0 or ratio disagreement (|r_m/r_y − 1| > 0.001) are still written to
  data_quality_breaks as SPLIT_SOURCE_MISMATCH (they are reported, not applied twice).
- yfinance-only splits with no massive counterpart within ±3 days are applied AND reported (reason e.g.
  SPLIT_SINGLE_SOURCE) so we can audit them.

## 2 (blocking). SQL semantic tests that run the REAL SQL
The apply-once test is pure Python and never runs the SQL (removing `WHERE rn = 1` leaves 61/61 passing).
Add tests that extract the actual CTE SQL from silver/08 (parse the file; do not re-type the SQL in the test), run it in
DuckDB (CI already installs duckdb; add duckdb to requirements.txt dev section or a requirements-dev note if one exists) against
small fixture tables, and assert the cumulative factor per bar:
- same-day both sources → factor 20 (applied once);
- AMZN massive 06-06 / yfinance 06-03 → factor 20 before 06-03 too, and adj_close continuity around the split (≈ +2%, not −95%);
- yfinance-only split → applied once and in data_quality_breaks as SPLIT_SINGLE_SOURCE;
- ratio disagreement same day → massive ratio used, mismatch reported;
- SQQQ reverse 5:1 (ratio 0.2) → factor 0.2.
If DuckDB can't parse a Databricks-only function, add a minimal, documented translation shim in the test (e.g. regex
replacing that one function) — never a hand-rewritten copy of the query.
Mutation proofs (in /tmp copies, report output): `WHERE rn = 1` → `WHERE 1=1` FAILS; removing the ±3-day suppression FAILS.

## 3 (blocking). API key leaks via error messages
In `_request_with_retry` (etl/corporate_actions.py ~345-355) the requests exception text includes the full URL with
apiKey=; it is wrapped into RuntimeError, printed (notebooks/refresh_bronze_corporate_actions.py ~435), stored in
report["failures"] and checkpoint error_text. `_redact_api_key` (~250) is never called.
Fix: never let a raw requests exception message escape the adapter — build your own message from status code + redacted
URL, and `raise ... from None` (so the chained exception with the URL isn't printed in tracebacks). Also redact at the
notebook boundary (failures, checkpoint error_text, prints) as defense in depth.
Tests (no network): a fake session raising requests.HTTPError / ConnectionError whose message contains
`apiKey=SECRET123` → assert "SECRET123" appears in NONE of: the raised exception str/repr, its __cause__/__context__ chain,
report["failures"], the checkpoint error_text, captured stdout/stderr/logs (capsys + caplog).
Mutation proof: remove redaction → test FAILS.

## 4. Minor: resume per source
In `both` mode `completed_symbols` ignores source; make the checkpoint key (symbol, source). Test.

## 5. Docs
docs/DATA_SCHEMAS.md + notebook docstring: the ±3-day same-event rule and reason codes SPLIT_SOURCE_MISMATCH /
SPLIT_SINGLE_SOURCE. Note that adjusted prices are back-adjusted (historical levels change when a later split is
loaded; returns are unaffected) — PIT consumers must use returns, not historical adjusted levels.

## Acceptance
- python -m pytest -q tests/bronze tests/silver tests/test_security.py all pass; pyspark hidden
  (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) same.
- .agents/mimo/VERDICT-corporate-actions-round6.md with counts + all mutation outputs. Commit everything.
