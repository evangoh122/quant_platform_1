# Verdict: corporate actions rounds 4+5 (69a46b4..HEAD)

Checker: Claude Sonnet subagent (DeepSeek out of credit)

## VERDICT: CHANGES_REQUESTED

Counts: `pytest tests/bronze tests/silver tests/test_security.py` = 327 passed, 13 skipped.
With pyspark hidden (nps path): `tests/bronze tests/silver` = 317 passed, 22 skipped.
Full `pytest -q` did not finish inside 120s (slow dirs outside this slice); not re-run to completion.
No tests deleted or weakened (7 removed lines, all replaced by stricter equivalents). No CRLF in changed files.
Commits 480bf2c ("chore:") and 2dc176d ("fix:") have empty-ish messages: process nit.

## Blocking findings

1. DOUBLE APPLICATION on near-date disagreement (silver/08_silver_ohlcv_day_adjusted.sql:133-160, join at :257).
   `_resolved_splits` dedupes only on exact (symbol, ex_date). Reproduced in DuckDB by running the real
   `_resolved_splits` + `_split_factors` SQL (/tmp/ca5-sem/sem.py): massive AMZN 20:1 on 2022-06-06 and
   yfinance 20:1 on 2022-06-03 gives cumulative factor 399.99 for 06-01/06-02, 20 for 06-03..06-05, 1 after.
   The split is applied twice, on two dates. Same-day case correctly yields 20. The +-3 day near-match is only
   reported to `_split_source_mismatch` (:~170-230); it is not used to suppress the lower-precedence row.
   Fix: collapse yfinance rows that lie within +-3 days of a massive row for the same symbol (anti-join) in the CTE.
2. API KEY LEAK in error paths (etl/corporate_actions.py:~345-355, `_request_with_retry`).
   `resp.raise_for_status()` and requests ConnectionError text embed the full URL including `apiKey=`.
   It is wrapped into `RuntimeError(f"... {last_exc}")`, then printed (notebooks/refresh_bronze_corporate_actions.py:435),
   stored in `report["failures"]` and written to the checkpoint `error_text` (:~440). Reproduced
   (/tmp/ca5-sem/leak.py): exception string contains the secret. `_redact_api_key` (:250) is dead code, never called.
   Fix: redact in every exception message (and use `from None`), including `__cause__`.
3. TESTS DO NOT PROVE THE ABOVE.
   - Apply-once test (tests/silver/test_ohlcv_day_adjusted.py:951-1030) is a pure-Python reference, never runs the SQL.
     Mutation: removing the dedupe (`WHERE rn = 1` -> `WHERE 1=1` in /tmp/ca5-mut-dedupe) leaves 61/61 passing. Mutation survives.
   - Redaction tests (tests/bronze/test_corporate_actions.py:1043-1068) test the helper in isolation only; logging
     the raw URL would not fail any test (and the leak in 2 exists today).
   Fix: execute the SQL view (DuckDB) with same-day and +-1-day fixtures; add an exception-path redaction test.

## Verified OK

- Pagination mutation (/tmp/ca5-mut-page, next_url=None): test_pagination_two_pages fails (1 failed, 80 passed).
- Massive adapter: split_ratio = split_to/split_from, ex_date = execution_date, next_url gets apiKey appended,
  bounded retry/backoff on 429/5xx, 401/403 raise PermissionError without key, exact ticker filter, invalid ratios skipped.
- Notebook: default source massive, VALID_SOURCES + `both`, globals().get("dbutils"), widgets in notebook mode (argv ignored),
  strict argparse in CLI, key from dbutils.secrets / env MASSIVE_API_KEY / SDK, fails closed.
- Silver: every split join (`_split_factors`, `_break_candidates`) uses `_resolved_splits`; the only other
  bronze_corporate_actions references are the mismatch view. MERGEs use explicit column lists (no `*`).
- Semantics note: `_resolved_splits` has no information_available_ts filter (neither did the baseline); precedence is by
  source only, so a yfinance row never wins due to a late massive row; PIT is not enforced in silver.
- Mismatch rule: |m/y-1|>0.001 and unmatched within +-3 days are emitted with explicit reason; but see finding 1.

## Minor
- Resume checkpoint `completed_symbols` ignores source in `both` mode (notebook ~:380).
