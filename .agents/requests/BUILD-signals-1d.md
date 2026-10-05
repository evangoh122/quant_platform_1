# BUILD: baseline signals — switch to a 1-trading-day horizon (owner decision 2026-10-05)

You are MiMo. Branch `review/post-submission` (stay on it). LF endings, never touch `.agents/dispatch.sh`. Do NOT run anything against
Databricks and never pass `--write`. COMMIT your work, one commit per item.

Why: gold_model_features has ONE snapshot per symbol per day (~00:00–01:00 UTC, i.e. after the US close); no snapshot is 30 min after another,
so the 30-minute label (ml/baseline_labels.forward_labels) leaves 0 training rows (Claude live run). Owner chose a 1-day horizon.

## 1. ml/baseline_labels.py — `daily_close_labels(features, closes, max_gap_days=5)`
- `closes`: one row per (symbol, trade_date) with `close` and `close_ts` (tz-aware UTC) = the LAST regular-session minute bar of that US/Eastern date.
- For each feature row (symbol, prediction_ts): D = the latest trade_date of that symbol with `close_ts <= prediction_ts`; N = the next trade_date
  after D for that symbol. label = 1.0 if close_N > close_D else 0.0; `label_ts = close_ts_N`. NaN label (and NaT label_ts) when D or N is missing
  or N - D > max_gap_days calendar days. Never use a close with close_ts > prediction_ts as close_D.
- Keep `forward_labels` (30-min) as is; `purged_split` and `refit_rows` are reused unchanged.
## 2. scripts/publish_baseline_signals.py
- Fetch daily closes with ONE aggregated warehouse query over silver_ohlcv: `is_regular_session = true`, `timespan = 'minute'`, group by symbol and
  `to_date(from_utc_timestamp(event_ts, 'America/New_York'))`, take the close of the max event_ts (`max_by(close, event_ts)`) and `max(event_ts)` as
  close_ts, limited to the symbols in gold_model_features. Table names constant; no user input in SQL.
- Use `daily_close_labels`, then `purged_split`, holdout AUC, scoring rows, `refit_rows`, refit, score. `horizon="1d"`,
  `model_version="baseline-logreg-v1-1d-2026-10-05"`. Print rows labelled, train/test sizes, cutoff, AUC, refit cutoff/rows, signal counts.
- `--write` still only MERGEs new signal_ids (unchanged). Update the module docstring to describe the 1-day label exactly.
## 3. Tests (tests/ml/test_baseline_labels.py; must fail on the current code — red phase in the verdict)
- snapshot after D's close → labelled from D→N; snapshot BEFORE D's close (same date) → uses the previous trading day as D;
- weekend: Friday snapshot labelled from Friday→Monday; gap > max_gap_days → NaN; last trading date → NaN; symbols never mix;
- a close with close_ts > prediction_ts is never used as close_D (look-ahead guard);
- integration: daily_close_labels → purged_split → refit_rows on a 3-symbol staggered fixture gives no train/refit row with label_ts after the cut.
- Named mutations (paste FAILED output): use `close_ts <= prediction_ts` → `trade_date <= prediction_ts.date()` (same-day look-ahead);
  drop the max_gap check; label from N+1 instead of N.
Acceptance: `python3 -m pytest tests/ml -q` green. Verdict `.agents/mimo/VERDICT-signals-1d.md`.
