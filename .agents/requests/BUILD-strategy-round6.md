# BUILD: strategy round 6 (MiMo)

DeepSeek returned CHANGES_REQUESTED (`.agents/deepseek/VERDICT-strategy-check3.md`). Read it first.

## 1. [Blocking] `strategies/backtest.py:~85-105`: the sign-flip ADV cap is wrong both ways
`increasing = |cur| > |prev|` conflates net magnitude with "a new leg is opened":
- `+0.4 → -0.4` (equal magnitude) opens the new short UNCAPPED.
- `+0.06 → -0.4` caps the close-out of the long, which must never be capped.

Fix: decompose each day's change per name into
- the **close leg**: movement from `prev` toward 0, capped at reaching 0. It is never capped.
- the **open leg**: movement beyond 0, or away from 0 on the same side as `prev`. Cap it at
  `cap_frac * adv / book_capital`.

Result:
- `new = prev + close_leg + clip(open_leg, ±cap)`.
- Same-side increase: open leg only, capped.
- Same-side reduction: close leg only, free.
- Flip: full close to 0 is free; the new side is capped.

Tests, each failing on the current code:
- `+0.4 → -0.4` with cap 0.02/day: day 1 = `-0.02`, then -0.04, …, converging to -0.4.
- `+0.06 → -0.4`, cap 0.02: day 1 = `-0.02`. The long is fully closed on the flip day.
- Existing tests keep passing: dropped name exits; same-side increase capped.

## 2. [Consistency] `strategies/residual_reversion.py:~185-189,244`: sigma vs min_obs
`_trailing_std` uses `min_periods=window`, so one gap kills `sigma` for 60 days, while the beta
tolerates `min_obs = ceil(0.8*window)`. Pass `min_obs` through and use
`rolling(window, min_periods=min_obs)` for sigma.
Test: a series with 10% gaps gets a non-NaN `s_score` once the window has ≥ min_obs valid residuals.

## 3. Changelog
In `strategies/run_residual_reversion.py`, add `CHANGELOG[5]` rows for these two fixes. Claude will
rerun live as r5.

## Rules
- `python3 -m pytest -q tests/strategies tests/ml` passes.
- `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/strategies` passes, with a sitecustomize
  that sets `sys.modules[m]=None` for pyspark, pyspark.sql, pyspark.sql.functions and
  pyspark.sql.types.
- Show in the verdict that each new test fails on the current code (/tmp copy).
- LF line endings. Don't touch `.agents/dispatch.sh` or `strategies/results/`. Commit. Write
  `.agents/mimo/VERDICT-strategy-round6.md`.
