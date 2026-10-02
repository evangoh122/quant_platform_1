# VERDICT: silver-gold round 7 — Codex

CHANGES_REQUESTED

1. The matrix invariant names all four sources and would catch the round-6 OHLCV leak, but it does not reliably check every contributed source feature.

   - OHLCV requires a matching bar at `prediction_ts`, so the round-6 matrix—whose timestamp was 60 seconds earlier—would fail: [pipelines/run_silver_gold.py:187](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:187).
   - Options validates only `put_call_ratio`; rows containing IV or volume features while that field is NULL are skipped: [pipelines/run_silver_gold.py:195](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:195).
   - SEC validates only `sec_sentiment_score`; a populated risk-factor change or material-event flag can be skipped: [pipelines/run_silver_gold.py:204](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:204).
   - COT validates only `cot_lev_money_zscore`; populated percentile-derived fields can be skipped when the z-score is NULL: [pipelines/run_silver_gold.py:213](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:213).
   - Matching only one feature value can also falsely associate the matrix value with a different historical row having the same value. The invariant needs source timestamps retained in the matrix or comparison of the complete latest-as-of source record.

2. The MERGE-key change is not safely handled by the build.

   The SQL documentation says a one-time truncate is required, but the implementation still performs only a MERGE on the new `(symbol, prediction_ts)` value: [gold/05_gold_model_features.sql:28](/home/jianj/code/qp1-sg/gold/05_gold_model_features.sql:28), [gold/05_gold_model_features.sql:98](/home/jianj/code/qp1-sg/gold/05_gold_model_features.sql:98). Truncation happens only when the operator explicitly supplies `--truncate`: [pipelines/run_silver_gold.py:266](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:266), [pipelines/run_silver_gold.py:276](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:276).

   Claude’s clean live rebuild proves the current table has no duplicates, but the code remains vulnerable: a deployment over round-6 data, or a late-arriving bar that changes a day’s maximum availability timestamp, inserts the new key without removing the old daily row. Both rows can pass the current OHLCV invariant because each timestamp may identify a real bar. The build should delete/reconcile obsolete symbol-day rows or rebuild this target automatically.

Other checks:

- COT enforces exactly 52 observations before emitting percentile or z-score values via the bounded count gate: [gold/04_gold_cot_features.sql:64](/home/jianj/code/qp1-sg/gold/04_gold_cot_features.sql:64), [gold/04_gold_cot_features.sql:107](/home/jianj/code/qp1-sg/gold/04_gold_cot_features.sql:107). Its percentile correctly ranks the feature value using the count strictly below it: [gold/04_gold_cot_features.sql:86](/home/jianj/code/qp1-sg/gold/04_gold_cot_features.sql:86).
- `ingest_ts` is sound for the repository’s current snapshot loader: it assigns one timestamp to the invocation and sets `participant_ts` to that same value: [notebooks/01_ingest_market_data.py:209](/home/jianj/code/qp1-sg/notebooks/01_ingest_market_data.py:209), [notebooks/01_ingest_market_data.py:265](/home/jianj/code/qp1-sg/notebooks/01_ingest_market_data.py:265), [notebooks/01_ingest_market_data.py:274](/home/jianj/code/qp1-sg/notebooks/01_ingest_market_data.py:274). One invocation can span multiple API calls, but no future ingest batch affects earlier rows. The partitioning is therefore point-in-time safe for this loader: [silver/03_silver_options_quotes.sql:50](/home/jianj/code/qp1-sg/silver/03_silver_options_quotes.sql:50).
- No regression found in trailing OHLCV windows: [gold/01_gold_ohlcv_features.sql:35](/home/jianj/code/qp1-sg/gold/01_gold_ohlcv_features.sql:35), [gold/01_gold_ohlcv_features.sql:78](/home/jianj/code/qp1-sg/gold/01_gold_ohlcv_features.sql:78).
- Options availability remains session-close plus publication buffer: [gold/02_gold_options_features.sql:69](/home/jianj/code/qp1-sg/gold/02_gold_options_features.sql:69).
- Minute availability remains `event_ts + INTERVAL 1 MINUTE`: [gold/01_gold_ohlcv_features.sql:22](/home/jianj/code/qp1-sg/gold/01_gold_ohlcv_features.sql:22).
- Requested offline tests passed: `14 passed in 0.96s`.
- No files were written.

