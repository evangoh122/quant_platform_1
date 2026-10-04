# VERDICT: strategy-round6 — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings

None — both blocking items from DeepSeek's check3 verdict are resolved.

## What was fixed

### 1. Sign-flip ADV cap (`strategies/backtest.py`)
The old `increasing = abs(cur) > abs(prev)` test conflated net magnitude with
"new leg opens". Two concrete failures fixed:

- **Equal-magnitude flip uncapped:** `+0.4 → -0.4` had `|cur|==|prev|`, so
  `increasing=False` and the new short opened fully in one day. Now day 1
  weight = -0.02 (capped), converging to -0.4 over ~20 days.

- **Close-out wrongly capped:** `+0.06 → -0.4` had `|target|>|prev|`, so the
  whole Δ was capped including the long close-out. Now the close leg (-0.06)
  is free and only the open leg (-0.4) is capped to -0.02.

Fix: decompose `dw = cur - prev` into:
- `close_leg`: moves `prev` toward 0 (capped at reaching 0, never ADV-capped)
- `open_leg`: remainder (ADV-capped at `cap_frac * ADV / book_capital`)

### 2. Sigma min_periods alignment (`strategies/residual_reversion.py`)
`_trailing_std` used `min_periods=window` (60) while the beta regression used
`min_obs = ceil(0.8*window)` (48). One gap in the trailing window killed sigma
for 60 days. Now `_trailing_std` accepts `min_periods` and `compute_residuals`
passes `min_obs`, so sigma uses the same gap tolerance as beta.

## New tests (all fail on old code, pass on fixed code)

| Test | Old code result | Fixed result |
|------|----------------|-------------|
| `test_sign_flip_equal_magnitude_capped` | day 1 = 0.0 (uncapped) | day 1 = -0.02 (capped) |
| `test_sign_flip_close_out_not_capped` | day 3 = +0.04 (close-out capped) | day 3 = -0.02 (close free, open capped) |
| `test_existing_dropped_name_exits` | pass | pass |
| `test_existing_same_side_increase_capped` | pass (old code happened to work for this case) | pass |
| `test_sigma_uses_min_obs_not_full_window` | 80 days starved (day 120+) | 0 days starved |

## Checks run
```
$ python3 -m pytest -q tests/strategies tests/ml
76 passed, 34 warnings in 83.71s

$ PYTHONPATH=/tmp python3 -m pytest -q tests/strategies   # no-pyspark sitecustomize
39 passed, 16 warnings in 5.64s

$ python3 _verify_old_failures.py   # old code reproduction
OLD code day 1: 0.0000 (expected -0.02) — FAIL
OLD code day 3: 0.0400 (expected -0.02) — FAIL
OLD code sigma starvation: 80 days — FAIL
```

## Non-blocking notes
- The practical impact on this backtest is small (the 1%-of-ADV budget for
  top-300 names is far above their neutralised weights, so the cap rarely
  binds), but the stated invariant was wrong in both directions.
- The sigma fix is consistency-only for the liquid top-300 universe (names
  trade continuously, so gaps are rare); it matters more for universes with
  thinner coverage.