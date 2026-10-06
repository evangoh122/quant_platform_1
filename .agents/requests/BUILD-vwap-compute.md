# BUILD-vwap-compute — compute VWAP instead of passing through an always-NULL vendor column

You are MiMo. Branch `fix/vwap-compute` in worktree /home/jianj/code/qp1-vwap (stay on it; `git branch --show-current` before every commit).
Shell rule: run `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-vwap && <cmd>'` directly, or write a script to `/home/jianj/code/qp1-vwap/.agentlogs/<name>.sh` and run
`wsl -d Ubuntu -- bash <path>`. No PowerShell wrappers, nothing in C:\temp. LF endings. Never touch `.agents/dispatch.sh`. Stage only files you change. Commit per item.
Do NOT run anything against Databricks (no live writes); Claude runs the live rebuild after review.

## Live evidence (Claude, 2026-10-06, SQL warehouse)
- `silver_ohlcv` minute bars: 23,377,478 rows, 39 symbols, `vwap` non-null = 0 (Massive flat files carry no vwap).
- `silver_ohlcv_day_adjusted`: 639,369 rows / 557 symbols, `vwap` and `adj_vwap` non-null = 0.
- `gold_ohlcv_features.vwap_deviation` non-null = 0; `gold_model_features.vwap_deviation` non-null = 0 of 40,983 → a dead model feature.

## Items
1. **gold/01_gold_ohlcv_features.sql — session VWAP.** In `lagged`, compute a trailing session VWAP over the SAME partition the file already uses for session_high/low
   (`PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`):
   `SUM(COALESCE(vwap, (high+low+close)/3.0) * volume) / NULLIF(SUM(volume), 0)` — the bar's own vendor vwap when present, else the typical price. Output it as `vwap`
   so `vwap_deviation = (close - vwap)/NULLIF(vwap,0)` keeps its formula. Strictly trailing (no future bars → PIT safe). Update the header comment.
2. **silver/08_silver_ohlcv_day_adjusted.sql — daily VWAP from minute bars.** Add a temp view `_minute_vwap` = per (symbol, trading date) `SUM(COALESCE(vwap,(h+l+c)/3)*volume)/NULLIF(SUM(volume),0)`
   from `silver_ohlcv WHERE timespan='minute'`, trading date = `DATE(from_utc_timestamp(event_ts, 'America/New_York'))`. In `_adjusted`: raw daily `vwap` = vendor vwap if
   non-null else `_minute_vwap`; `adj_vwap` adjusted as today. Add column `vwap_source STRING` ('vendor' | 'minute_bars' | NULL) — add it to the CREATE TABLE and add an
   idempotent `ALTER TABLE ... ADD COLUMNS` path the way the repo does for other added columns (find the existing pattern; pipelines/run_silver_gold.py has
   `ensure_model_availability_columns`). Symbols with no minute bars keep NULL vwap — NEVER fabricate a daily typical-price proxy.
   Also add `vwap_source` to db/schema_contract.py / docs/DATA_SCHEMAS.md / analytics_nl/data/source_schemas_v1.yaml wherever the adjusted-table columns are listed, and fix any test that pins that list.
3. **pipelines/run_silver_gold.py — guard.** In `run_checks`, fail if gold_ohlcv_features has rows with volume>0 in the run window but zero non-null `vwap_deviation`, and log the
   non-null ratio for `silver_ohlcv_day_adjusted.adj_vwap` by `vwap_source`.

## Tests (DuckDB executing the REAL SQL, same shim style as tests/silver/test_silver_sql_semantics.py; no Spark, no network)
- `tests/gold/test_gold_vwap_sql.py`: extract the real `lagged`/feature SELECT from gold/01; fixture of 3 minute bars, one day, vwap NULL: (h,l,c,vol)=(11,9,10,100),(12,10,11,300),(13,11,12,0)
  → session vwap bar1=10, bar2=(10*100+11*300)/400=10.75, bar3=10.75 (zero volume keeps prior), vwap_deviation bar2=(11-10.75)/10.75. A second day's first bar resets
  (not blended with day 1). A bar with vendor vwap uses it instead of typical price.
- `tests/silver/test_silver_vwap_sql.py`: real `_minute_vwap` + `_adjusted` views; symbol with minute bars → vwap_source='minute_bars', value matches; symbol with vendor vwap →
  'vendor'; symbol without either → NULL vwap and NULL source; a 2:1 split before the bar → adj_vwap = vwap/2; a minute bar at 2026-03-10T01:00Z (ET 2026-03-09 21:00) lands on 2026-03-09.
- Mutations you must run (in a /tmp `git archive` copy, never `cp -r` the worktree) and record FAILED output for: (a) drop the typical-price fallback, (b) remove the session
  partition's DATE(event_ts) (blend days), (c) use UTC date instead of ET in `_minute_vwap`, (d) ROWS ... FOLLOWING (future leak), (e) fabricate a proxy for symbols with no minute bars.
- Run the full suite: `python -m pytest -q` (report counts).
Verdict `.agents/mimo/VERDICT-vwap-compute.md` with commands, counts and mutation outputs.
