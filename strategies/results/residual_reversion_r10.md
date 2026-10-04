# Residual mean-reversion — round 10 (real data)

**Price source:** `silver_ohlcv_day_adjusted` (split-adjusted)
**Masked breaks:** 174 (symbol, date) pairs excluded from signals and P&L

Market/industry residual mean-reversion on the point-in-time top-300
tradable universe (`gold_tradable_universe`), 2023-01-04 → 2026-10-01.
Industry labels are the repo `config/tickers.yaml` taxonomy, **not** GICS.

## What changed vs r9

| # | Change | Effect |
|---|---|---|
| 1 | Prices now come from `silver_ohlcv_day_adjusted` (Massive split data; `adj_close`) instead of unadjusted `bronze_ohlcv_day` | r9 treated every split as a crash (e.g. AMZN 2022-06-06 −94.9%); adjusted return that day is +1.99%. Net max drawdown fell from −51.2% (r9) to −9.5% |
| 2 | 174 masked break days (`data_quality_breaks.is_masked`: ticker reuse/renames, collapses, leveraged-ETF resets) excluded from signals and P&L | Unexplained jumps no longer drive entries or P&L |

r9 headline for comparison: net Sharpe −0.363, OOS net Sharpe −0.623, net max drawdown −51.2% — **superseded** (unadjusted prices).

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
| annualised return | 0.0385 | 0.0067 | -0.0252 |
| Sharpe | 0.680 | 0.118 | -0.445 |
| max drawdown | -0.0721 | -0.0949 | -0.1618 |
| hit rate (daily) | 0.3434 | | |
| avg turnover (daily, one-way) | 0.2848 | | |
| average hold (days) | 3.85 | | |

## Ablation — unconditioned vs gated by `breadth_regime == NARROW`

**Caveat:** The gated comparison below is an **in-sample / full-period exploratory ablation**.
It is not evidence of an edge. The gated net Sharpe at 2× costs is -0.375 and the deflated Sharpe ratio (DSR) is 0.000. This result should not be used to justify live deployment without out-of-sample validation on a held-out period.

| metric | unconditioned | gated (NARROW only) |
|---|---:|---:|
| annualised return (net) | 0.0067 | 0.0043 |
| Sharpe (net) | 0.118 | 0.109 |
| Sharpe (net @ 2x) | -0.445 | -0.375 |

## Walk-forward (max_hold chosen on training folds only)

| configs compared | 3 (max_hold in [3, 5, 10]) |
|---|---:|
| out-of-sample net Sharpe | 0.075 |
| out-of-sample net annualised return | 0.0053 |
| deflated Sharpe (Bailey/LdP, n_trials=3) | 0.000 |

## Capacity

- median total 1%-of-ADV budget across the universe: $3,819,194,086
- shorts pay an explicit borrow haircut by liquidity bucket (no borrow data exists;
  liquid 0.25 bps/day, medium 0.75, illiquid 2.00 — a stated assumption, never zero).

## Limitations

- Masked break days (unexplained jumps such as ticker reuse, renames, leveraged ETFs)
  have `return_1d IS NULL` in silver. Positions held across a masked day earn **0** that
  day — the return is NaN and skipped by the P&L summation. No signal is generated on
  masked days.
- **Masked-day P&L is dropped, not exit-priced.** A position held across a masked day earns 0 that day. If a masked
  break was a genuine adverse move, net P&L is flattered. Not yet quantified; a follow-up should count masked days that
  fall on held positions and re-run charging them.
- **Deflated Sharpe trial count is understated.** `n_trials=3` counts only the walk-forward `max_hold` grid. The strategy
  was iterated over ~12 review rounds while results were visible, and the NARROW-regime ablation is a further variant, so
  the true number of trials is larger and the DSR (already 0.000) is, if anything, optimistic.
- **No untouched holdout.** All 939 days were seen during development; the walk-forward OOS figure is the closest proxy.
- **Conclusion:** after split adjustment the strategy is roughly flat net of costs (net Sharpe 0.118, OOS 0.075) and
  negative at 2× costs, with DSR 0.000. There is **no evidence of a tradable edge**; this is a research baseline, not a
  deployment candidate.
