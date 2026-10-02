# BUILD-REQUEST: silver-gold — ROUND 4 (look-ahead leak)

**Branch:** `slice/silver-gold` · **Builder:** DeepSeek · **Validators:** Claude, then Codex
**Gate:** PR #8 BLOCKED. Read `.agents/codex/VERDICT-silver-gold-and-ml.md` (PR #8 section).

## 1. Fix the session high/low look-ahead (critical)

`gold/01_gold_ohlcv_features.sql:26-27`:

```sql
MAX(high) OVER (PARTITION BY symbol, DATE(event_ts)) AS session_high,
MIN(low)  OVER (PARTITION BY symbol, DATE(event_ts)) AS session_low
```

No `ORDER BY`, so the window is the **whole day**: a 09:31 bar sees the 15:59
high. That leaks into `dist_session_high/low` while the row claims availability
at the bar's timestamp. Make it trailing:
`OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)`.

## 2. Audit every window function in `silver/` and `gold/`

For every `OVER (...)`: a partition-wide aggregate with no `ORDER BY` and no
trailing frame, any `FOLLOWING`, `LEAD`, or a full-history mean/stddev used as a
z-score baseline is a leak. List every window you checked, with the verdict,
in your verdict file.

## 3. Fix COT percentile / z-score

`gold/04_gold_cot_features.sql:41` ranks by `report_date`, not by positioning
value, and `:43-49` use expanding history rather than a 52-week window. Compute
a true trailing 52-report percentile of the **value**, and a bounded
52-report-window mean/stddev for the z-score.

## 4. Make the PIT test test the real build

`tests/gold/test_pit_leakage.py` only exercises a standalone comparator that the
build never calls. Replace it with a **future-invariance test**, the standard
check for look-ahead:
- Pick a sample (e.g. 2 symbols × 2 days).
- Compute the gold features from silver data **truncated at time t**, and again
  from the full data.
- Every feature row with `feature_ts <= t` must be **identical** in both runs.

Run it against the real SQL logic (via databricks-connect on a small filtered
input, or by executing the same SQL on a local DataFrame). Demonstrate it
**fails** against the old session-high SQL and **passes** against the fix.
Paste both outputs. Mark it `@pytest.mark.databricks` if it needs the
workspace.

## 5. Rebuild and verify

Re-run `gold_ohlcv_features` (23.4M rows) and downstream `gold_model_features`
and `gold_cot_features` through the existing MERGE paths. Paste before/after
row counts — they should be unchanged — and a query showing `session_high` on
a day's first bar equals that bar's own high.

## Constraints

Do not touch `agent/`, `db/`, `api/`, `frontend/`, `ml/`, `conftest.py`,
`pytest.ini`, `requirements*.txt`. Keep options IV NULL-outside-snapshot behaviour.
**Commit your work.** Write `.agents/deepseek/VERDICT-silver-gold-round4.md`.
