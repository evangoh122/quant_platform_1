# BUILD-REQUEST: silver-gold — ROUND 5 (options availability timestamp)

**Branch:** `slice/silver-gold` · **Builder:** DeepSeek · **Validators:** Claude, then Codex

## Round 4 verified

The session high/low fix is correct **and live**: on 2026-08-28 SPY's first bar,
`dist_session_high = close/high - 1` of that bar alone (-8.68e-4). COT percentile
fix accepted. Keep all of it.

## Defect 1 — daily options features are available a session too early (critical)

Measured by the coordinator:

```
bronze_options_day.event_ts time-of-day:            04:00:00  (8,605,813 rows, all of them)
gold_options_features.information_available_ts tod: 04:00 (12,859) · 05:00 (6,531)
```

The provider timestamps a **daily** bar at the **start** of the day (04:00 UTC =
midnight New York). The bar's volume covers the **whole session**.
`gold/02_gold_options_features.sql:160` sets
`information_available_ts = day.last_ts`, which is that 04:00 start stamp.

`gold_model_features` joins with `information_available_ts <= prediction_ts`, so
a 15:00 UTC prediction on day *d* sees day *d*'s full options volume, hours
before it exists. Every intraday row with options features is contaminated.

**Fix:** a daily options aggregate for day *d* becomes available only after that
session closes. Set `information_available_ts` = 16:00 America/New_York on day
*d*, converted to UTC (DST-aware: `to_utc_timestamp(<d> 16:00, 'America/New_York')`),
plus a publication buffer (default 30 minutes; make it a named constant). Then
rebuild `gold_options_features` and `gold_model_features`.

**Audit the same pattern everywhere**, not just here: any daily or period
aggregate whose timestamp marks the *start* of its window. Check
`bronze_ohlcv_day`-derived features, COT (`release_ts` must be the official
release, not `report_date`), and SEC. List each source and its availability rule
in your verdict.

## Defect 2 — `is_stale` uses the day's last quote

`silver/03_silver_options_quotes.sql:32,41`:
`MAX(participant_ts) OVER (PARTITION BY underlying)` is the latest quote of the
**whole day**, so a quote is flagged stale because later quotes exist. Make it
point-in-time: compare against the latest quote **at or before** that quote's
own timestamp across the underlying's chain (a trailing window), or against the
snapshot time if the table is defined as a single snapshot — and document which
definition you chose.

## Defect 3 — the PIT test missed this

Round 4's future-invariance test covers OHLCV only, so it could not see this
leak. Extend it:
- Add an **availability invariant**, run as a SQL assertion after each build:
  for every gold row, `information_available_ts >= end of the source window it
  aggregates`. For daily options that is ≥ the session close for `feature_ts`'s
  date. The build should fail when it is violated.
- Add a future-invariance case for `gold_options_features` and
  `gold_model_features`.
- Show the assertion **failing** against the current table (the 04:00 stamps),
  then passing after the fix. Paste both.

## Verify

Paste: `information_available_ts` time-of-day distribution after the fix
(expect ~20:30 UTC in summer, ~21:30 UTC in winter), and row counts before and
after the rebuild (unchanged).

## Constraints

Do not touch `agent/`, `db/`, `api/`, `frontend/`, `ml/`, `conftest.py`,
`pytest.ini`, `requirements*.txt`. Keep IV NULL outside the snapshot date.
**Commit your work.** Write `.agents/deepseek/VERDICT-silver-gold-round5.md`.
