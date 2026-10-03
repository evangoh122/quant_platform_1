# BUILD-REQUEST: silver-gold — ROUND 6 (minute-bar availability, narrow)

**Branch:** `slice/silver-gold` · **Builder:** DeepSeek · **Validators:** Claude, then Codex

## Round 5 verified live — keep it

- `gold_options_features` availability now 20:30 / 21:30 UTC (16:00 New York + 30 min, DST-aware).
- 0 rows available before their own session close; row counts unchanged (19,390 / 43,345).
- `gold_model_features` honours it: end-of-day predictions (23:5x UTC) use same-day options;
  rows stamped 00:59 UTC correctly use the prior day.

## The defect — minute bars are stamped at their START

Measured: every SPY day in `bronze_ohlcv` runs **04:00 → 23:59** (1-min bars), i.e. bars
are labelled `[t, t+1min)` — Polygon's documented convention (`t` = window start).

`gold/01_gold_ohlcv_features.sql:79` sets `information_available_ts = event_ts`, with a
comment at `:7` asserting `event_ts` is the bar close. It is not. A bar's close is known
only at `event_ts + 1 minute`. All 23,377,478 rows claim availability one bar early.

Magnitude: a one-minute look-ahead on a 30-minute horizon. Real, but small — do not
over-engineer.

## Fix

1. `information_available_ts = event_ts + INTERVAL 1 MINUTE` for minute bars. Derive the
   interval from `timespan` rather than hard-coding, so any non-minute bars are correct.
2. Correct the comment at `:7`.
3. Apply the same rule anywhere else bar-stamped data sets availability (check
   `silver_ohlcv`-derived features and anything built from `bronze_ohlcv_day`, whose daily
   bars should be available at session close, like options).
4. Extend the round-5 availability invariant: for minute features,
   `information_available_ts >= event_ts + bar interval`. Show it failing on the current
   table, then passing.
5. Rebuild `gold_ohlcv_features` (23.4M) and `gold_model_features`. Paste before/after
   counts (unchanged) and the new `information_available_ts - feature_ts` distribution
   (expect 60 seconds).

Do not touch `agent/`, `db/`, `api/`, `frontend/`, `ml/`, `conftest.py`, `pytest.ini`,
`requirements*.txt`. **Commit your work.** Write `.agents/deepseek/VERDICT-silver-gold-round6.md`.
