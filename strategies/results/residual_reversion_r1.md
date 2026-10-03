# Residual mean-reversion — round 1 baseline (real data)

Market/industry residual mean-reversion on the point-in-time top-300
tradable universe (`gold_tradable_universe`), 2023-01-04 → 2026-09-04.
Industry labels are the repo `config/tickers.yaml` taxonomy, **not** GICS.

## Configuration

- universe: top 300 by trailing 60-day median dollar volume (recency 5, min history 252)
- residual regression: rolling window 60 days, lookback L = 5
- entry: long s <= -2.5, short s >= +2.5; exit |s| < 0.5
- book capital: $10,000,000; target gross 1.0 (100% long / 100% short)
- dates: 921 trading days; purged walk-forward folds: 5

## Results — unconditional baseline (max_hold = 5)

| metric | gross | net | net @ 2x costs |
|---|---:|---:|---:|
| annualised return | -0.0075 | -0.0442 | -0.0809 |
| Sharpe | -0.054 | -0.318 | -0.581 |
| max drawdown | -0.3120 | -0.3290 | -0.3975 |
| hit rate (daily) | 0.3939 | | |
| avg turnover (daily, one-way) | 0.3289 | | |
| average hold (days) | 3.84 | | |

## Ablation — unconditioned vs gated by `breadth_regime == NARROW`

| metric | unconditioned | gated (NARROW only) |
|---|---:|---:|
| annualised return (net) | -0.0442 | 0.0032 |
| Sharpe (net) | -0.318 | 0.073 |
| Sharpe (net @ 2x) | -0.581 | -0.421 |

## Walk-forward (max_hold chosen on training folds only)

| configs compared | 3 (max_hold in [3, 5, 10]) |
|---|---:|
| out-of-sample net Sharpe | -0.378 |
| out-of-sample net annualised return | -0.0691 |
| deflated Sharpe (Bailey/LdP, n_trials=3) | 0.000 |

## Capacity

- median total 1%-of-ADV budget across the universe: $3,791,330,569
- shorts pay an explicit borrow haircut by liquidity bucket (no borrow data exists;
  liquid 0.25 bps/day, medium 0.75, illiquid 2.00 — a stated assumption, never zero).
