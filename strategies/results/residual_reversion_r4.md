# Residual mean-reversion — round 4 (real data)

Market/industry residual mean-reversion on the point-in-time top-300
tradable universe (`gold_tradable_universe`), 2023-01-04 → 2026-10-01.
Industry labels are the repo `config/tickers.yaml` taxonomy, **not** GICS.

## What changed vs r3

| # | Fix | Files | Rationale |
|---|-----|-------|-----------|
| 1 | Missing returns are excluded, not treated as zero | `strategies/residual_reversion.py` | Per-row validity mask; the regression uses the true count of valid days and is NaN below `min_obs` = ceil(0.8 x window) |
| 2 | Exits are never blocked by the ADV cap | `strategies/backtest.py` | Only increases are capped; ADV is forward-filled for names that leave the universe, so a position can always be reduced to zero |
| 3 | Universe median requires a full 60-session window | `gold/06_gold_tradable_universe.sql` | `med_adv_60d` is NULL unless all 60 prior sessions have volume, matching the pandas reference `min_periods=60` |
| 4 | Breadth SMA50 requires a full 50-day window | `gold/07_gold_regime_features.sql` | The first 49 dates are labelled MIXED instead of BROAD/NARROW from a partial average |

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
| annualised return | -0.0562 | -0.0884 | -0.1205 |
| Sharpe | -0.256 | -0.403 | -0.549 |
| max drawdown | -0.5004 | -0.5154 | -0.5487 |
| hit rate (daily) | 0.3468 | | |
| avg turnover (daily, one-way) | 0.2875 | | |
| average hold (days) | 3.85 | | |

## Ablation — unconditioned vs gated by `breadth_regime == NARROW`

**Caveat:** The gated comparison below is an **in-sample / full-period exploratory ablation**.
It is not evidence of an edge. The gated net Sharpe at 2× costs is -0.264 and the deflated Sharpe ratio (DSR) is 0.000. This result should not be used to justify live deployment without out-of-sample validation on a held-out period.

| metric | unconditioned | gated (NARROW only) |
|---|---:|---:|
| annualised return (net) | -0.0884 | 0.0082 |
| Sharpe (net) | -0.403 | 0.203 |
| Sharpe (net @ 2x) | -0.549 | -0.264 |

## Walk-forward (max_hold chosen on training folds only)

| configs compared | 3 (max_hold in [3, 5, 10]) |
|---|---:|
| out-of-sample net Sharpe | -0.519 |
| out-of-sample net annualised return | -0.1768 |
| deflated Sharpe (Bailey/LdP, n_trials=3) | 0.000 |

## Capacity

- median total 1%-of-ADV budget across the universe: $3,819,194,086
- shorts pay an explicit borrow haircut by liquidity bucket (no borrow data exists;
  liquid 0.25 bps/day, medium 0.75, illiquid 2.00 — a stated assumption, never zero).
