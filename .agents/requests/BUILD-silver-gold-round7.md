# BUILD-REQUEST: silver-gold — ROUND 7

**Branch:** `slice/silver-gold` · **Builder:** DeepSeek · **Validators:** Claude, then Codex
Read `.agents/codex/VERDICT-silver-gold-round6.md`. Codex confirmed the OHLCV windows are
trailing, the future-invariance test runs production SQL with a working negative control,
MERGE keys are stable, and options/COT/SEC joins enforce availability. Keep all of it.

## 1. Model matrix uses its last bar one minute early (critical)

`gold/05_gold_model_features.sql:25-36`: `daily_base` sets
`prediction_ts = MAX(feature_ts)` (the last bar's **start**) and joins
`f.feature_ts = db.prediction_ts` with no availability check. Since round 6, a bar is
available at `feature_ts + 1 minute`, so every row uses its final bar 60s early.

Fix: set `prediction_ts` to the bar's availability, i.e.
`MAX(information_available_ts)`, and join on
`f.information_available_ts = db.prediction_ts` (or select the latest OHLCV row with
`information_available_ts <= prediction_ts`).

**This changes the MERGE key `(symbol, prediction_ts)`.** A plain re-run would insert
new rows next to the old leaking rows. Rebuild `gold_model_features` cleanly (delete the
affected rows or rebuild the table inside the same run), and paste before/after counts
proving **no duplicates**. Do NOT use `COUNT(DISTINCT symbol, DATE(prediction_ts))`:
4,143 symbol-days legitimately have two rows because a winter session's last bar falls
after midnight UTC (e.g. 00:59). Instead prove: (a) `COUNT(*) = COUNT(DISTINCT symbol,
prediction_ts)`; (b) total rows unchanged at **43,345**; (c) no row still carries the old
bar-start `prediction_ts` for a session that now has a bar-close row.

**Resuming:** a previous attempt was stopped mid-edit. Its partial edits are committed
(`wip(silver-gold): round-7 edits in progress`). Review them, keep what is correct, and finish.

## 2. The build invariant must check the model matrix

`pipelines/run_silver_gold.py:137` checks only source-table timestamp construction, so
the leaking matrix passes. Add a matrix-level assertion: for every
`gold_model_features` row, each contributing source row's `information_available_ts`
must be `<= prediction_ts`. If the matrix does not retain source availability
timestamps, add the needed columns or assert via a join back to the sources. Show it
**failing** on the current table, then passing after the fix.

## 3. COT warm-up

`gold/04_gold_cot_features.sql`: the first 51 reports get partial-window percentile and
z-score values, contradicting the documented NULL behaviour at `:22`. Require a full 52
reports (`COUNT(*) = 52` within the bounded window), else NULL.

## 4. `is_stale` must stay point-in-time when more snapshots arrive

`silver/03_silver_options_quotes.sql:40,47` compares each quote with the max timestamp
of the **whole table**. Harmless for today's single snapshot, but an appended snapshot
would retroactively change older rows. Scope the reference to an explicit snapshot /
capture key (e.g. the ingest batch), or to the latest quote at or before the row's own
timestamp. Document which.

## Verify (live)

- `gold_model_features`: `prediction_ts - last bar feature_ts` = 60s; no duplicates.
- COT: first 51 reports per market have NULL percentile/z-score.
- Row counts for every other gold table unchanged.

Do not touch `agent/`, `db/`, `api/`, `frontend/`, `ml/`, `conftest.py`, `pytest.ini`,
`requirements*.txt`. **Commit your work.** Write `.agents/deepseek/VERDICT-silver-gold-round7.md`.
