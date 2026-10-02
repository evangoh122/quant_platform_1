# Residual mean-reversion — round 2 (real data)

Market/industry residual mean-reversion on the point-in-time top-300
tradable universe (`gold_tradable_universe`), 2023-01-04 → 2026-09-04.
Industry labels are the repo `config/tickers.yaml` taxonomy, **not** GICS.

## What changed vs r1

| # | Fix | Files | Rationale |
|---|-----|-------|-----------|
| 1 | Universe look-ahead eliminated | `gold/06_gold_tradable_universe.sql` | Dense calendar×symbols grid; recency counts last 5 *market sessions*, not the symbol's own bars |
| 2 | Industry factors date-specific | `strategies/residual_reversion.py`, `strategies/run_residual_reversion.py` | NaN returns stay NaN; industry factor uses per-date eligible member count; universe mask prevents pre-IPO returns |
| 3 | ADV cap constrains execution | `strategies/backtest.py` | Weight changes capped at 1% of ADV; capped positions carried forward; zero-ADV names cannot be traded |
| 4 | Breadth-gated caveat | this file | Gated result is an in-sample exploratory ablation (see below) |

## Configuration

- universe: top 300 by trailing 60-day median dollar volume (recency 5, min history 252)
- residual regression: rolling window 60 days, lookback L = 5
- entry: long s <= -2.5, short s >= +2.5; exit |s| < 0.5
- book capital: $10,000,000; target gross 1.0 (100% long / 100% short)
- dates: 921 trading days; purged walk-forward folds: 5
- ADV cap: 1% of trailing median dollar volume per name per day

## Results — unconditional baseline (max_hold = 5)

| metric | gross | net | net @ 2x costs |
|---|---:|---:|---:|
| annualised return | -0.0277 | -0.0635 | -0.0994 |
| Sharpe | -0.144 | -0.331 | -0.518 |
| max drawdown | -0.4280 | -0.4371 | -0.4792 |
| hit rate (daily) | 0.3717 | | |
| avg turnover (daily, one-way) | 0.2984 | | |
| average hold (days) | 4.24 | | |

## Ablation — unconditioned vs gated by `breadth_regime == NARROW`

**Caveat:** The gated comparison below is an **in-sample / full-period exploratory ablation**.
It is not evidence of an edge. The gated net Sharpe at 2× costs is -0.183 and the deflated Sharpe ratio (DSR) is 0.003. This result should not be used to justify live deployment without out-of-sample validation on a held-out period.

| metric | unconditioned | gated (NARROW only) |
|---|---:|---:|
| annualised return (net) | -0.0635 | 0.0144 |
| Sharpe (net) | -0.331 | 0.346 |
| Sharpe (net @ 2x) | -0.518 | -0.183 |

## Walk-forward (max_hold chosen on training folds only)

| configs compared | 3 (max_hold in [3, 5, 10]) |
|---|---:|
| out-of-sample net Sharpe | -0.619 |
| out-of-sample net annualised return | -0.1757 |
| deflated Sharpe (Bailey/LdP, n_trials=3) | 0.000 |

## Capacity

- median total 1%-of-ADV budget across the universe: $3,791,330,569
- shorts pay an explicit borrow haircut by liquidity bucket (no borrow data exists;
  liquid 0.25 bps/day, medium 0.75, illiquid 2.00 — a stated assumption, never zero).
