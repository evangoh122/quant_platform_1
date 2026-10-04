# Residual mean-reversion — round 6 (real data)

Market/industry residual mean-reversion on the point-in-time top-300
tradable universe (`gold_tradable_universe`), 2023-01-04 → 2026-10-01.
Industry labels are the repo `config/tickers.yaml` taxonomy, **not** GICS.

## What changed vs r5

| # | Fix | Files | Rationale |
|---|-----|-------|-----------|
| 1 | Same-side reductions are never ADV-capped | `strategies/backtest.py` | Round 6 routed same-side partial reductions (e.g. +0.4 to +0.2) into the capped open leg. Any move toward zero is now free and only moves away from zero are capped; a seeded 500-sequence property test enforces the invariants |

## Configuration

- universe: top 300 by trailing 60-day median dollar volume (recency 5, min history 252)
- residual regression: rolling window 60 days, lookback L = 5
- entry: long s <= -2.5, short s >= +2.5; exit |s| < 0.5
- book capital: $10,000,000; target gross 1.0 (100% long / 100% short)
- dates: 939 trading days; purged walk-forward folds: 5
- ADV cap: 1% of trailing median dollar volume per name per day

## Results — unconditional baseline (max_hold = 5)

| metric | gross | net | net @ 2x costs |
|---|---:|---:|---:|
| annualised return | -0.0478 | -0.0803 | -0.1129 |
| Sharpe | -0.216 | -0.363 | -0.510 |
| max drawdown | -0.5030 | -0.5121 | -0.5411 |
| hit rate (daily) | 0.3493 | | |
| avg turnover (daily, one-way) | 0.2911 | | |
| average hold (days) | 3.86 | | |

## Ablation — unconditioned vs gated by `breadth_regime == NARROW`

**Caveat:** The gated comparison below is an **in-sample / full-period exploratory ablation**.
It is not evidence of an edge. The gated net Sharpe at 2× costs is -0.163 and the deflated Sharpe ratio (DSR) is 0.000. This result should not be used to justify live deployment without out-of-sample validation on a held-out period.

| metric | unconditioned | gated (NARROW only) |
|---|---:|---:|
| annualised return (net) | -0.0803 | 0.0127 |
| Sharpe (net) | -0.363 | 0.310 |
| Sharpe (net @ 2x) | -0.510 | -0.163 |

## Walk-forward (max_hold chosen on training folds only)

| configs compared | 3 (max_hold in [3, 5, 10]) |
|---|---:|
| out-of-sample net Sharpe | -0.623 |
| out-of-sample net annualised return | -0.2350 |
| deflated Sharpe (Bailey/LdP, n_trials=3) | 0.000 |

## Capacity

- median total 1%-of-ADV budget across the universe: $3,819,194,086
- shorts pay an explicit borrow haircut by liquidity bucket (no borrow data exists;
  liquid 0.25 bps/day, medium 0.75, illiquid 2.00 — a stated assumption, never zero).
