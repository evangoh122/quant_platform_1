# BUILD corporate-actions round 8 (builder: MiMo) — test gaps only; production code verified

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/corporate-actions. Descriptive commits. LF endings.
NEVER delete or weaken existing tests. DeepSeek verdict: .agents/deepseek/VERDICT-corporate-actions-round7.md (Massive-only verified).

1 (blocking). `test_mutation_drop_source_filter_fails` (tests/silver/test_silver_sql_semantics.py:321-372) is vacuous: it only asserts
   len(pre_split) > 0, and massive/yfinance rows share fetched_ts. Rewrite: fixture with massive AMZN 20:1 (fetched_ts 2026-01-01) and a
   non-massive row for the same (symbol, ex_date) with a DIFFERENT ratio (e.g. 15.0) and a LATER fetched_ts (2026-02-01). Positive test: real
   SQL → factor exactly 20.0. Mutation test: extracted SQL with the source filter removed → factor != 20.0 (assert the exact wrong value 15.0),
   proving the filter matters.
2 (blocking). Price-jump break logic must be tested against the REAL SQL. Extract `_break_candidates` / `_classified_breaks` (and whatever they
   depend on) from silver/08 at test time and run them in DuckDB on fixtures:
   (a) unexplained −50% move, no split → exactly one break row with the expected classification/columns;
   (b) AMZN split day with matching ~+2% adjusted move → no break row;
   (c) split day whose raw move doesn't match the ratio within tolerance → one break row (expected classification).
   Mutation tests on the extracted SQL: delete the break-candidate predicate (or make it always false) → (a) FAILS. Keep the existing
   `_compute_break` Python reference tests too.
3. duckdb in requirements: add to requirements.txt (or a dev/test requirements file if one exists) to match CI.
Acceptance: python3 -m pytest -q tests/bronze tests/silver tests/test_security.py all pass; pyspark hidden
(PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) same.
.agents/mimo/VERDICT-corporate-actions-round8.md with counts + mutation outputs. Commit everything.
