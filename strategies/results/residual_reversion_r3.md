# Residual mean-reversion — round 3 (real data)

Market/industry residual mean-reversion on the point-in-time top-300
tradable universe (`gold_tradable_universe`), 2023-01-04 → 2026-10-01.
Industry labels are the repo `config/tickers.yaml` taxonomy, **not** GICS.

## What changed vs r2

| # | Fix | Files | Rationale |
|---|-----|-------|-----------|
| 1 | Min-history gate now counts own trading sessions | `gold/06_gold_tradable_universe.sql`, `strategies/universe.py` | `COUNT(dollar_volume)` instead of `COUNT(*)` — pre-listing NULL rows no longer inflate history |
| 2 | Date range derived from data | `strategies/run_residual_reversion.py` | No more hardcoded dates in results header |

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
| annualised return | -0.0264 | -0.0629 | -0.0993 |
| Sharpe | -0.141 | -0.335 | -0.529 |
| max drawdown | -0.4215 | -0.4327 | -0.4758 |
| hit rate (daily) | 0.3753 | | |
| avg turnover (daily, one-way) | 0.3009 | | |
| average hold (days) | 4.26 | | |

## Ablation — unconditioned vs gated by `breadth_regime == NARROW`

**Caveat:** The gated comparison below is an **in-sample / full-period exploratory ablation**.
It is not evidence of an edge. The gated net Sharpe at 2× costs is -0.203 and the deflated Sharpe ratio (DSR) is 0.000. This result should not be used to justify live deployment without out-of-sample validation on a held-out period.

| metric | unconditioned | gated (NARROW only) |
|---|---:|---:|
| annualised return (net) | -0.0629 | 0.0136 |
| Sharpe (net) | -0.335 | 0.330 |
| Sharpe (net @ 2x) | -0.529 | -0.203 |

## Walk-forward (max_hold chosen on training folds only)

| configs compared | 3 (max_hold in [3, 5, 10]) |
|---|---:|
| out-of-sample net Sharpe | -0.411 |
| out-of-sample net annualised return | -0.0973 |
| deflated Sharpe (Bailey/LdP, n_trials=3) | 0.000 |

## Capacity

- median total 1%-of-ADV budget across the universe: $3,820,256,706
- shorts pay an explicit borrow haircut by liquidity bucket (no borrow data exists;
  liquid 0.25 bps/day, medium 0.75, illiquid 2.00 — a stated assumption, never zero).
