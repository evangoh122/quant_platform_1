# Build: Decision Dashboard Phase 0a — data-correctness fixes

Builder: MiMo. Checker: DeepSeek. Then Codex final, Opus final, PR + CodeRabbit (follow AGENTS.md if present, else .agents/PROTOCOL.md).
Branch: `feat/decision-dashboard-p0` (worktree /home/jianj/code/qp1-decision-p0). Do not deploy, start the Databricks app, touch Lakebase, or write shared data.
Commit on this branch only; do not create other branches.

## Why
Codex and Opus found data-correctness defects that would make a trading dashboard mislead. Fix exactly these four; nothing else.

## Fixes
1. **Spark options read is nondeterministic.** `agent/tools_retrieval.py` `get_options_features` PySpark branch (~line 107-116) applies `.limit()` with no `orderBy`. Order by `feature_ts` DESC (use the real column name from `_OPTIONS_COLS`) before `.limit()`, matching the warehouse path (`_build_options_query`). Do the same for any sibling Spark read in that file that limits without ordering newest-first (market features) — check and fix only if it has the same defect.
2. **"252 days" are calendar days.** `api/routes/market.py` computes `start_dt = end_dt - timedelta(days=days)`. The parameter means trading days. Convert N trading days to a start date using a weekday-aware helper (skip Sat/Sun; NYSE holidays optional — if you do not add a holiday calendar, name the helper/docstring "weekday approximation" and return a `detail` note in the Envelope freshness so the UI can say `calendar_limited`). Put the helper in a small new module `api/trading_days.py` with a pure function `start_for_trading_days(end: date, n: int) -> date`. Update the docstring. Default of 252 must now yield ~252 weekdays back (~1 year).
3. **Null must not become zero.** `api/routes/portfolio.py` (~line 40) coerces `unrealized_pnl` and `realized_pnl` null to 0. Preserve `None`: change the `Position` schema in `api/schemas.py` so `unrealized_pnl` (and `market_price`) are `Optional[float]`, serialize None as null. Update `frontend/src/api/types.ts` and `frontend/src/screens/PaperPortfolio.tsx` minimally so null renders as an em dash "—" (not 0, not NaN) and is excluded from totals with a visible "unpriced" note. Touch no other frontend file.
4. **Options volume-anomaly z-score has no minimum-window gate.** `gold/02_gold_options_features.sql` (~line 83-87) computes the z-score over `ROWS BETWEEN 19 PRECEDING AND CURRENT ROW` with no count guard. Add a window count (`COUNT(total_volume) OVER w`) and output NULL for the z-score unless count >= 20. Keep column names unchanged.

## Test shape (MANDATORY — tests may only call production code/SQL; never copy their logic)
- Fix 1: call the real `get_options_features` with a fake Spark chain (mock `_spark()` returning a recording DataFrame stub, `_has_pyspark=True`); assert `orderBy` is called with a descending `feature_ts` ordering BEFORE `limit`. Also a behavioral test with a stub that returns shuffled rows only when not ordered.
- Fix 2: unit-test `start_for_trading_days` with fixed dates (a known Wednesday back 5 trading days = prior Wednesday; spans weekends; n=252 lands ~1y). Plus an API test via the existing `tests/api/test_market.py` fixtures asserting the start_time passed to `get_market_features` equals the helper output (monkeypatch `get_market_features` to capture args; freeze "now").
- Fix 3: API test with a fake positions row where `unrealized_pnl`/`market_price` are None; assert JSON has null (not 0). Frontend vitest: render `PaperPortfolio` with a null-P&L position; assert "—" present, no "$0.00" for that cell, and total excludes it with an "unpriced" note.
- Fix 4: execute the real SQL file's z-score expression on a tiny table. If a SQL engine is not available in tests (check how other `tests/gold` tests do it), follow that existing pattern; otherwise parse the production SQL file text and assert the guard clause exists AND run a pure-pandas/duckdb equivalent only if duckdb is already a dependency. Do not add dependencies.

## Mutations that MUST make a test fail (run each in an isolated `git archive` copy, never git in a cp -r copy; record the transcript in the evidence file)
- M1 remove the `orderBy` in tools_retrieval.
- M2 replace the helper call in market.py with `timedelta(days=days)`.
- M3 change `float(r.get("unrealized_pnl") or 0)` back to the coercion.
- M4 remove the count guard from the SQL.
- M5 make `start_for_trading_days` ignore weekends.

## Acceptance
`pytest` for the touched areas (`tests/api`, `tests/gold`, `tests/agent`) and in `frontend/`: `npx tsc --noEmit`, `npx vitest run`, `npm run build` all pass. If you create `.agents/run-*.sh`, add `export PATH="$HOME/.nvm/versions/node/v26.5.0/bin:$PATH"` at the top.
Write evidence to `.agents/mimo/VERDICT-decision-p0a.md`. Commit everything. Finish with exactly one line:
`BUILD DONE | status: <SUCCESS|FAILURE> | sha: <40-char SHA or NO_COMMIT> | branch: feat/decision-dashboard-p0 | evidence: .agents/mimo/VERDICT-decision-p0a.md`
