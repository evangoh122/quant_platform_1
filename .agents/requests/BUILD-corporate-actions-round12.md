# BUILD corporate-actions round 12 (builder: MiMo) — test the REAL adjustment SQL

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/corporate-actions. Descriptive commits. LF. NEVER delete or weaken tests.
Reviewer verdict: .agents/reviewer/VERDICT-corporate-actions-r4.md. Its blocker (notebook header) was fixed by Claude in the latest commit — don't touch it.

1. The silver adjustment math is only tested against a Python re-implementation; two mutations survived all 92 silver tests (adj_close = close * cum,
   and adj_volume = volume / cum). Add DuckDB tests that extract the `_adjusted` view (and the CTEs it depends on) from
   silver/08_silver_ohlcv_day_adjusted.sql at test time and run it on fixtures: (a) a two-split symbol (cumulative product), (b) a reverse split,
   (c) the ex-date bar is on the new basis. Assert exact adj_close and adj_volume values. Template from the reviewer's probe:
   .agents/requests/ca-adjusted-probe-template.py (if present). Mutations (copy via `git archive HEAD | tar -x -C /tmp/<dir>`, paste output):
   adj_close = close * cum → FAILS; adj_volume = volume / cum → FAILS.
2. Runbook: document first-write-wins for (symbol, ex_date, source) conflicts and that conflict_rows > 0 must be investigated (add a WARNING log line
   when conflict_rows > 0). Note the job defaults to mode dry-run with no schedule (document how to run write mode).
Acceptance: python3 -m pytest -q tests/bronze tests/silver tests/test_security.py all pass; pyspark hidden
(PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps). .agents/mimo/VERDICT-corporate-actions-round12.md. Commit.
