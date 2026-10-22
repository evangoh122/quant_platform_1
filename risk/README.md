# Volatility & risk-sizing layer (Phase 1)

A small, reusable Polars layer that answers one question: **does
volatility-aware sizing improve net risk-adjusted performance versus fixed
sizing?** It is a library plus a seeded synthetic experiment; it does not touch
live data, Spark, Databricks, or execution code.

## Quick start

```python
import polars as pl
from risk.config import load_config
from risk.estimators import estimate_pair
from risk.regimes import label_regimes
from risk.compare import build_signal, compare_sizers
from risk.pair_backtest import backtest_vol_pair
from risk.sizing import size

cfg = load_config()
estimates = estimate_pair(panel, cfg.estimators, cfg.columns)  # date, vol_a/b, corr
regimes = label_regimes(estimates, cfg.regimes)
signal = build_signal(panel, cfg.signals, cfg.columns)
weights = size(signal, estimates, cfg.sizing)                  # date, w_a, w_b
result = backtest_vol_pair(panel, weights, cfg.backtest, columns=cfg.columns)
table = compare_sizers(panel, cfg)                            # all four sizers
```

`panel` is a long frame with `date` (`pl.Date`) and adjusted `open_a`,
`close_a`, `open_b`, `close_b` columns. Run the experiment with
`python -m risk.run_compare`; it writes `risk/results/p1_compare.md`.

## What is estimated

* EWMA volatility, covariance and correlation (`span`, `adjust=False`,
  `min_samples`, sample `ddof=1` via `ewm_var(bias=False)`), annualized with
  `252`.
* Rolling realized volatility for the configured 5/20/60-session windows,
  `ddof=1`.
* Overnight gap volatility (close `t-1` to open `t`) and intraday volatility
  (open `t` to close `t`) separately.
* A past-only 252-session volatility percentile (`risk/regimes.py`). With fewer
  than 252 usable observations it is null and the regime is `unknown`, never a
  fabricated number (important for short histories such as a 2023-launch ETF).
* A volatility floor (default 1% annualized) applied at the sizing boundary.

## Sizers

One signature: `size(signal_or_pair, estimates, params) -> date, w_a, w_b`.
`params.method` selects `equal_dollar`, `inverse_vol`, `covariance_aware` or
`vol_target`. The pair hedge ratio is `h = clip(vol_a / vol_b, 0.25, 3.0)`
(equivalently `sqrt(var_a / var_b)`), spread variance is
`var_a + h^2 var_b - 2 h cov` floored at `0.05^2`, and
`scale = min(target_vol / spread_vol, max_gross / (1 + h))`.
`vol_target` additionally multiplies by the alpha signal clipped to
`[-signal_cap, signal_cap]` **and** scales the book by
`alpha / max(1, |alpha|)`, so gross exposure stays at or below `max_gross` for
any configured cap. Because of that denominator, any `signal_cap` above 1 has
**no effect** on the final weights: with `|alpha| >= 1` the factor is the
unit-alpha book (`+1` or `-1`), so a cap above 1 never changes `w_a` or `w_b`
and `signal_cap` only matters below 1. `signal_cap` must be a positive finite
number, and `risk/config.py` validates this when the config is loaded, not on a
directly constructed parameter object.

Every sizer -- including `equal_dollar`, whose formula uses none of the
estimates -- requires a finite signal and a complete, finite estimate set
(`vol_a`, `vol_b`, `corr`). A null, NaN or infinite value in any of them yields
exactly zero weight on both legs, and the check runs on the raw estimates
*before* the correlation is clipped, so an infinite correlation cannot become a
maximum-size book. Missing risk estimates never produce a position.

## Execution and costs

Signals are decided at the close of `t` and fill at the open of `t+1`; P&L is
open-to-open and row `t` is earned by the book *held* over `open t-1 -> open t`,
which is the book filled at `open t-1`. That is two structural shifts, matching
`strategies/backtest.py` (`desired.shift(1)` for fills, then `weights.shift(1)`
against returns); a single shift would let a weight decided at the close earn
the overnight gap into its own fill price. It is covered by a shock test and a
fill-price test. Transaction costs are a configurable 5/10/15 bps per side on
`sum |delta w|`, with an optional ADV-participation mode implemented in Polars
and parity-tested against `strategies.cost_model.cost_per_trade`. Borrow is
charged only on the short notional of the book **held** over each open-to-open
interval (`w_a_held`, `w_b_held`) -- the same book that earns `gross_return`,
not the book filled at that row's open -- using the daily rate from
`strategies.cost_model.CostParams` (no borrow feed exists, so this is a stated
assumption).

## Assumptions and limitations

* **Adjusted prices only for returns.** The lakehouse adjusted OHLCV columns
  carry a global current-scale adjustment; returns derived from them are
  approved, adjusted *levels* are never used as features.
* Estimators use log **close-to-close** returns while P&L is **open-to-open**.
  This deliberate mix keeps the estimator on the most reliable series; it
  introduces a small timing mismatch between the vol estimate and the traded
  return, documented rather than hidden.
* `turnover = sum |delta w|` ignores intraday weight drift (no rebalancing
  between fills), so costs are a lower bound when prices drift.
* Borrow buckets are an assumption, not a measured securities-lending curve.
* `sharpe`, `realized_vol_gross` and `realized_vol_net` share one configured
  `ddof` (`backtest.sharpe_ddof`; default 0 matches `strategies/backtest.py`),
  so switching the convention moves all three together.
* The synthetic experiment uses seeded GARCH-like shocks. It proves the
  plumbing (estimators, lag, floors, caps, costs, reporting), **not alpha**.
  No claim is made about real MAGS/SOXX or any instrument.
* No pandas bridge in the layer: all data frames are Polars; `strategies.cost_model` is imported only for its scalar cost helpers (the request explicitly allows this); numpy only generates synthetic shocks.

All parameters live in `risk/config.yaml`; nothing strategy-specific is
hardcoded in the modules.
