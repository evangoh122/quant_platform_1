# A/B/C/D Ablation Results

> **NOTE: synthetic demonstration.** The live Unity Catalog gold tables
> (`gold_ohlcv_features`, `gold_options_features`, `gold_sec_features`,
> `gold_cot_features`, `gold_model_features`, `silver_ohlcv`) were all
> **empty (0 rows)** at build time, so the study below ran on the
> deterministic synthetic dataset in `ml/synthetic_data.py`, which mirrors
> the real schema. The pipeline is data-agnostic: point `ml/run_ablation.py`
> at the warehouse read path once live data lands. Treat the numbers as
> pipeline validation only, not as market findings.

Seed: 42 · n_symbols: 6 · n_bars: 400 · splits: 5 · min_train: 60

| Arm | Feature set | Model | ROC-AUC | Dir. acc | Brier | IC | Sharpe | MaxDD | Hit rate | Turnover | Avg hold | p95 lat (ms) |
| :-- | :-- | :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| A | OHLCV | baseline | 0.494 | 0.519 | 0.259 | -0.031 | 1.43 | -0.390 | 0.519 | 0.203 | 4.84 | 2.09 |
| A | OHLCV | challenger | 0.512 | 0.509 | 0.288 | 0.025 | -1.39 | -0.207 | 0.509 | 0.410 | 2.42 | 4.78 |
| B | OHLCV+options | baseline | 0.502 | 0.519 | 0.261 | -0.020 | 0.59 | -0.364 | 0.519 | 0.280 | 3.53 | 2.09 |
| B | OHLCV+options | challenger | 0.508 | 0.512 | 0.287 | 0.006 | -1.26 | -0.273 | 0.512 | 0.406 | 2.44 | 4.78 |
| C | OHLCV+options+SEC | baseline | 0.560 | 0.530 | 0.274 | 0.136 | 2.12 | -0.354 | 0.530 | 0.145 | 6.73 | 2.09 |
| C | OHLCV+options+SEC | challenger | 0.568 | 0.559 | 0.303 | 0.160 | 7.62 | -0.234 | 0.559 | 0.155 | 6.31 | 4.78 |
| D | OHLCV+options+SEC+COT | baseline | 0.562 | 0.553 | 0.293 | 0.123 | 5.38 | -0.305 | 0.553 | 0.112 | 8.64 | 2.09 |
| D | OHLCV+options+SEC+COT | challenger | 0.558 | 0.540 | 0.316 | 0.145 | 7.23 | -0.343 | 0.540 | 0.132 | 7.37 | 4.78 |
