# Residual mean-reversion — round 10 (real data)

> **PLACEHOLDER** — to be populated by the live rerun with split-adjusted prices.
> Claude runs the rerun after round 12 build completes.

**Price source:** `silver_ohlcv_day_adjusted` (split-adjusted)

## What changed vs r9

| # | Fix | Files | Rationale |
|---|-----|-------|-----------|
| 1 | Split-adjusted prices from silver_ohlcv_day_adjusted | `strategies/run_residual_reversion.py`, `strategies/config.yaml` | bronze_ohlcv_day is NOT split-adjusted (AMZN 2022-06-06 shows −94.9%). Now uses `adj_close` from `silver_ohlcv_day_adjusted` by default; `--price-table bronze_ohlcv_day` falls back to raw prices with a loud WARNING |
| 2 | Masked break days excluded from signals and P&L | `strategies/run_residual_reversion.py` | Returns on (symbol, event_date) where `return_1d IS NULL` in silver or `data_quality_breaks.is_masked` are set to NaN — no signal or P&L contribution on masked days. Positions held across a masked day earn 0 that day |

## Configuration

- universe: top 300 by trailing 60-day median dollar volume (recency 5, min history 252)
- residual regression: rolling window 60 days, lookback L = 5
- entry: long s <= -2.5, short s >= +2.5; exit |s| < 0.5
- book capital: $10,000,000; target gross 1.0 (50% long / 50% short)
- ADV cap: 1% of trailing median dollar volume per name per day

## Limitations

- Masked break days (unexplained jumps such as ticker reuse, renames, leveraged ETFs)
  have `return_1d IS NULL` in silver. Positions held across a masked day earn **0** that
  day — the return is NaN and skipped by the P&L summation. No signal is generated on
  masked days.