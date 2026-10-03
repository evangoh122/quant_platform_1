# Residual mean-reversion — round 7 (real data)

Market/industry residual mean-reversion on the point-in-time top-300
tradable universe (`gold_tradable_universe`), 2023-01-04 → 2026-10-01.
Industry labels are the repo `config/tickers.yaml` taxonomy, **not** GICS.

## What changed vs r6

| # | Fix | Files | Rationale |
|---|-----|-------|-----------|
| 1 | Exit/reduction costs charged on full executed notional | `strategies/backtest.py` | `compute_costs` was re-capping orders through `scale_order_to_adv_cap`, charging costs on at most 1% of ADV even for large exits. Now charges on the actual executed notional with true participation for slippage |
| 2 | Universe pandas matches SQL dense-grid semantics | `strategies/universe.py` | Reindex each symbol onto the full market calendar before rolling so missing sessions are NaN rows (matching SQL NULL rows), not absent rows |
| 3 | Z-score guard counts non-NULL column values | `gold/07_gold_regime_features.sql` | `COUNT(*)` counted all rows in window regardless of NULL `rsp_spy_ratio`; `AVG`/`STDDEV` ignore NULLs, so partial windows produced z-scores. Changed to `COUNT(rsp_spy_ratio)` |
| 4 | Leverage wording corrected to 50%/50% | `strategies/run_residual_reversion.py` | Gross 1.0 with dollar neutrality is 50% long / 50% short, not 100%/100% |

## Configuration

- universe: top 300 by trailing 60-day median dollar volume (recency 5, min history 252)
- residual regression: rolling window 60 days, lookback L = 5
- entry: long s <= -2.5, short s >= +2.5; exit |s| < 0.5
- book capital: $10,000,000; target gross 1.0 (50% long / 50% short)
- dates: 939 trading days; purged walk-forward folds: 5
- ADV cap: 1% of trailing median dollar volume per name per day

## Results — unconditional baseline (max_hold = 5)

| metric | gross | net | net @ 2x costs |
|---|---:|---:|---:|
| annualised return | -0.0478 | -0.0846 | -0.1214 |
| Sharpe | -0.216 | -0.382 | -0.548 |
| max drawdown | -0.5030 | -0.5162 | -0.5524 |
| hit rate (daily) | 0.3484 | | |
| avg turnover (daily, one-way) | 0.2911 | | |
| average hold (days) | 3.86 | | |

## Ablation — unconditioned vs gated by `breadth_regime == NARROW`

**Caveat:** The gated comparison below is an **in-sample / full-period exploratory ablation**.
It is not evidence of an edge. The gated net Sharpe at 2× costs is -0.278 and the deflated Sharpe ratio (DSR) is 0.000. This result should not be used to justify live deployment without out-of-sample validation on a held-out period.

| metric | unconditioned | gated (NARROW only) |
|---|---:|---:|
| annualised return (net) | -0.0846 | 0.0103 |
| Sharpe (net) | -0.382 | 0.251 |
| Sharpe (net @ 2x) | -0.548 | -0.278 |

## Walk-forward (max_hold chosen on training folds only)

| configs compared | 3 (max_hold in [3, 5, 10]) |
|---|---:|
| out-of-sample net Sharpe | -0.636 |
| out-of-sample net annualised return | -0.2399 |
| deflated Sharpe (Bailey/LdP, n_trials=3) | 0.000 |

## Capacity

- median total 1%-of-ADV budget across the universe: $3,819,194,086
- shorts pay an explicit borrow haircut by liquidity bucket (no borrow data exists;
  liquid 0.25 bps/day, medium 0.75, illiquid 2.00 — a stated assumption, never zero).
