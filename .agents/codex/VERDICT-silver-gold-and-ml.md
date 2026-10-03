# VERDICT: PR #8 silver-gold and PR #9 ml-hardening — Codex

PR #8 — CHANGES_REQUESTED

Blocking findings:

- Intraday lookahead exists in OHLCV features. [gold/01_gold_ohlcv_features.sql](/home/jianj/code/qp1-sg/gold/01_gold_ohlcv_features.sql:26) computes session high and low over the entire day without an ordered trailing frame. Early bars therefore use later prices; those leaked values become `dist_session_high/low` at lines 63–64 while claiming availability at the current bar timestamp on line 77.
- The PIT test is disconnected from the actual build. [tests/gold/test_pit_leakage.py](/home/jianj/code/qp1-sg/tests/gold/test_pit_leakage.py:61) proves only that a standalone in-memory timestamp comparator raises. `pit_guard` is never invoked by a production runner, and [gold/05_gold_model_features.sql](/home/jianj/code/qp1-sg/gold/05_gold_model_features.sql:68) does not retain source availability timestamps that could be validated afterward. Consequently, the test cannot detect the real session-high leak above.
- COT “52w percentile” is not a trailing value percentile. [gold/04_gold_cot_features.sql](/home/jianj/code/qp1-sg/gold/04_gold_cot_features.sql:41) ranks by `report_date`, not positioning value, and lines 43–49 use expanding-history averages/stddev rather than a bounded 52-week window. This is PIT-safe for the aggregate functions under Spark’s default ordered frame, but the resulting advertised features are incorrect.

PIT/source-key review:

- SEC correctly propagates `accepted_ts`: [gold/gold_sec_features.py](/home/jianj/code/qp1-sg/gold/gold_sec_features.py:111).
- COT correctly publishes `release_ts`: [gold/04_gold_cot_features.sql](/home/jianj/code/qp1-sg/gold/04_gold_cot_features.sql:57).
- Model joins enforce availability `<= prediction_ts`: [gold/05_gold_model_features.sql](/home/jianj/code/qp1-sg/gold/05_gold_model_features.sql:37).
- Options use a trailing 20-row window and do not forward-fill snapshot IV: [gold/02_gold_options_features.sql](/home/jianj/code/qp1-sg/gold/02_gold_options_features.sql:57).
- The reviewed gold MERGEs use stable target keys and are row-count idempotent, although `processed_ts` is intentionally rewritten on matched rows.

Offline PIT helper tests: `6 passed`.

PR #9 — CHANGES_REQUESTED

Blocking findings:

- Triple-barrier labelling is implemented but not selectable in the real ablation path. [ml/run_ablation.py](/home/jianj/code/qp1-ml/ml/run_ablation.py:47) exposes no label-method option, while [ml/synthetic_data.py](/home/jianj/code/qp1-ml/ml/synthetic_data.py:70) always calls the fixed-horizon labeler. The triple-barrier function is therefore an isolated utility rather than an ablation choice.
- Neutralisation silently does nothing on the actual supplied matrix. [ml/features.py](/home/jianj/code/qp1-ml/ml/features.py:431) returns the input unchanged when `market_beta` or `industry` is absent, and the synthetic/runner path never adds either field. The runner nevertheless reports neutralisation enabled through [ml/train.py](/home/jianj/code/qp1-ml/ml/train.py:248). Its regression is performed separately per timestamp, so it does not fit a temporal model on future dates, but it currently provides no neutralisation in the exercised pipeline.
- The deflated Sharpe trial count is hard-coded to four at [ml/evaluate.py](/home/jianj/code/qp1-ml/ml/evaluate.py:233), regardless of how many feature-set/model/label configurations were tried. With the optional challenger, the runner evaluates at least eight arm/model combinations. Moreover, DSR is calculated over individual cross-sectional rows rather than a timestamp-aggregated strategy return series, making its sample size and annualisation misleading.

Items that passed scrutiny:

- Purging operates on unique timestamp groups, preserving cross-sectional rows together, and removes training events whose inclusive label intervals overlap validation: [ml/train.py](/home/jianj/code/qp1-ml/ml/train.py:91).
- Embargo timestamps are selected immediately after validation and excluded from later training: [ml/train.py](/home/jianj/code/qp1-ml/ml/train.py:112).
- Triple-barrier volatility is trailing-only and evaluated at the event timestamp: [ml/features.py](/home/jianj/code/qp1-ml/ml/features.py:351).
- The purge and embargo tests exercise concrete removed indices: [tests/ml/test_walk_forward.py](/home/jianj/code/qp1-ml/tests/ml/test_walk_forward.py:42).

Requested offline command result: `20 passed, 5 warnings in 2.91s`.

