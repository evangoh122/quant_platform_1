# VERDICT: silver-gold rounds 4-6 — Codex

CHANGES_REQUESTED

1. `gold_model_features` still violates its own availability rule. The daily spine sets `prediction_ts` to the last bar’s `feature_ts`, i.e. the bar’s start ([gold/05_gold_model_features.sql](/home/jianj/code/qp1-sg/gold/05_gold_model_features.sql:25)). It then joins that bar directly on `f.feature_ts = db.prediction_ts` without requiring `f.information_available_ts <= db.prediction_ts` ([gold/05_gold_model_features.sql](/home/jianj/code/qp1-sg/gold/05_gold_model_features.sql:35)). Because minute features are now available at `feature_ts + 1 minute` ([gold/01_gold_ohlcv_features.sql](/home/jianj/code/qp1-sg/gold/01_gold_ohlcv_features.sql:22)), every model row uses its final OHLCV bar one minute before it is available. Either advance `prediction_ts` to the bar’s availability timestamp or select the latest OHLCV row available as of the intended prediction time.

2. The build invariant does not detect that model-matrix leak. It is genuinely executed after normal gold builds and raises on violations ([pipelines/run_silver_gold.py](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:218), [pipelines/run_silver_gold.py](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:150)), but it checks only source-table timestamp construction. It never checks that features included in `gold_model_features` were available at `prediction_ts` ([pipelines/run_silver_gold.py](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:137)). Thus the currently leaking matrix passes the build.

3. COT’s bounded calculations do not implement the stated full 52-report requirement. The percentile self-join is correctly bounded to rows `rn - 51` through `rn` and ranks the feature value rather than report date ([gold/04_gold_cot_features.sql](/home/jianj/code/qp1-sg/gold/04_gold_cot_features.sql:79)). The z-score windows are also bounded to 52 reports ([gold/04_gold_cot_features.sql](/home/jianj/code/qp1-sg/gold/04_gold_cot_features.sql:61)). However, no `COUNT = 52` condition exists, so the first 51 reports receive partial-window percentile/z-score values, contradicting the documented `NULL` behavior ([gold/04_gold_cot_features.sql](/home/jianj/code/qp1-sg/gold/04_gold_cot_features.sql:22)). COT availability is correctly keyed on aggregated `release_ts` ([gold/04_gold_cot_features.sql](/home/jianj/code/qp1-sg/gold/04_gold_cot_features.sql:34), [gold/04_gold_cot_features.sql](/home/jianj/code/qp1-sg/gold/04_gold_cot_features.sql:114)).

4. `is_stale` is not generally point-in-time safe. Each quote is compared with the maximum timestamp across the entire source table ([silver/03_silver_options_quotes.sql](/home/jianj/code/qp1-sg/silver/03_silver_options_quotes.sql:40), [silver/03_silver_options_quotes.sql](/home/jianj/code/qp1-sg/silver/03_silver_options_quotes.sql:47)). It happens to be harmless for the currently observed single-timestamp snapshot, but a later appended snapshot will retroactively change earlier rows’ `is_stale` values using future data. The window must be scoped to an explicit snapshot/capture key or use a row-specific point-in-time reference.

Other conclusions:

- The OHLCV windows are trailing and no longer use later bars. All rolling windows end at `CURRENT ROW`.
- The future-invariance test executes the production feature query extracted from the SQL, with limited DuckDB substitutions ([tests/gold/test_pit_leakage.py](/home/jianj/code/qp1-sg/tests/gold/test_pit_leakage.py:47)). Its negative control substitutes the old whole-day high/low clauses and successfully detects the leak ([tests/gold/test_pit_leakage.py](/home/jianj/code/qp1-sg/tests/gold/test_pit_leakage.py:145)).
- The availability changes did not modify any MERGE key. OHLCV remains keyed by `(symbol, feature_ts)`, options by `(symbol, feature_ts)`, COT by `(mapped_asset, report_date)`, and model features by `(symbol, prediction_ts)`. No duplication is expected from these timestamp changes.
- Options/COT/SEC model joins correctly enforce `information_available_ts <= prediction_ts`.

Offline test result:

- Requested command failed during collection because two silver tests import the removed `db.database` module.
- Independently runnable suites passed: gold `10 passed`; silver conversions `18 passed`.
- Workspace remained unchanged.

