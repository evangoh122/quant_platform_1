# Phase 1 — volatility-aware sizing vs fixed sizing (synthetic)

**This is a seeded synthetic experiment. It proves the plumbing, not alpha.**
No claim is made about real MAGS/SOXX or any live instrument.

- seed: `20261022`
- days: `1500`
- pair correlation of shocks: `0.8`
- target vol: `0.1`
- max gross: `2.0`
- OOS fraction: `0.5`
- signal: `momentum_z` (lookback `20`)

Execution is identical across variants: signal at close t, fill at open
t+1, open-to-open P&L, flat per-side cost plus borrow on short notional.

`vol_target` multiplies the covariance-aware book by the alpha
magnitude; `covariance_aware` uses its sign. The `momentum_z` reference
signal varies in magnitude, so the two variants differ.

| variant | cost_bps | oos_sharpe | ann_return | realized_vol_gross | target_vol | vol_gap | max_drawdown | gross_exposure_avg | net_exposure_avg | turnover_avg | borrow_cost_total | net_pnl_total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| equal_dollar | 5.0000 | -0.4870 | -0.0618 | 0.1171 | 0.1000 | 0.0171 | -0.2736 | 1.0000 | 0.0000 | 0.1893 | 0.0094 | -0.1696 |
| equal_dollar | 10.0000 | -0.6906 | -0.0840 | 0.1171 | 0.1000 | 0.0171 | -0.2951 | 1.0000 | 0.0000 | 0.1893 | 0.0094 | -0.2406 |
| equal_dollar | 15.0000 | -0.8926 | -0.1056 | 0.1171 | 0.1000 | 0.0171 | -0.3219 | 1.0000 | 0.0000 | 0.1893 | 0.0094 | -0.3116 |
| inverse_vol | 5.0000 | -0.6737 | -0.0712 | 0.1016 | 0.1000 | 0.0016 | -0.2811 | 1.0000 | 0.0129 | 0.2053 | 0.0093 | -0.2045 |
| inverse_vol | 10.0000 | -0.9223 | -0.0950 | 0.1016 | 0.1000 | 0.0016 | -0.3089 | 1.0000 | 0.0129 | 0.2053 | 0.0093 | -0.2814 |
| inverse_vol | 15.0000 | -1.1658 | -0.1182 | 0.1016 | 0.1000 | 0.0016 | -0.3374 | 1.0000 | 0.0129 | 0.2053 | 0.0093 | -0.3584 |
| covariance_aware | 5.0000 | -0.6370 | -0.0772 | 0.1150 | 0.1000 | 0.0150 | -0.3027 | 1.1632 | 0.0040 | 0.2737 | 0.0109 | -0.2191 |
| covariance_aware | 10.0000 | -0.9289 | -0.1086 | 0.1150 | 0.1000 | 0.0150 | -0.3351 | 1.1632 | 0.0040 | 0.2737 | 0.0109 | -0.3217 |
| covariance_aware | 15.0000 | -1.2141 | -0.1389 | 0.1150 | 0.1000 | 0.0150 | -0.3721 | 1.1632 | 0.0040 | 0.2737 | 0.0109 | -0.4244 |
| vol_target | 5.0000 | -0.8962 | -0.0835 | 0.0922 | 0.1000 | 0.0078 | -0.2936 | 0.8627 | 0.0030 | 0.2440 | 0.0081 | -0.2467 |
| vol_target | 10.0000 | -1.2239 | -0.1113 | 0.0922 | 0.1000 | 0.0078 | -0.3301 | 0.8627 | 0.0030 | 0.2440 | 0.0081 | -0.3382 |
| vol_target | 15.0000 | -1.5479 | -0.1382 | 0.0922 | 0.1000 | 0.0078 | -0.3660 | 0.8627 | 0.0030 | 0.2440 | 0.0081 | -0.4297 |

`realized_vol_gross` is the annualized volatility of the OOS gross
return path; `vol_gap` is its absolute distance from the configured
target. `turnover_avg` is the mean daily `sum |delta w|` (two-way
traded notional) and ignores intraday weight drift.
