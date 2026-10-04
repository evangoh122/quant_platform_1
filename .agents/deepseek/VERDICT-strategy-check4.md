===VERDICT START===
# VERDICT: strategy-residual-reversion round 6 re-check — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 6

Re-verified the round-6 fix (commit `1d956ea`) on `slice/strategy-residual-reversion`
against my check3 blocking finding, plus the sigma change and the r5 results. All
scratch work under `/tmp`; nothing committed or pushed.

## Blocking findings

- [strategies/backtest.py:104-122] The round-6 decomposition fixes the *sign-flip*
  cases but **regresses the same-side partial reduction**. For a name held long
  `+0.4` whose target drops to `+0.2` (same side, magnitude shrinks, no sign flip),
  `same_side = sign(prev)*sign(cur) > 0` is `True`, so `close_raw = 0` and
  `open_leg = dw = -0.2`. The reduction is treated as an "open leg" and ADV-capped,
  contradicting the module's own docstring — *"Reductions toward zero are never
  capped"* (backtest.py:74-75) and the inline comment *"open_leg: ... further away
  from 0 on the same side"* (backtest.py:103), which is false for a reduction.
  Reproduced: target `[0.4]*20 + [0.2]*8` with cap 0.02/day yields weights
  `0.4, 0.38, 0.36, 0.34, 0.32, 0.30, 0.28, 0.26, 0.24` — the reduction is throttled
  at 0.02/day instead of landing at 0.2 in one day. This is a regression: the round-5
  code `increasing = abs(cur) > abs(prev) + 1e-15` (75e0e7d) did **not** cap this case.
  Full exits are unaffected (target→0 makes `sign(cur)=0`, so `same_side=False` and
  `close_leg=-prev` is free), so `test_position_liquidates_when_adv_becomes_nan` still
  passes; there is no test for the partial-reduction case. The fix is to route the
  same-side reduction into `close_leg` (movement toward 0), not `open_leg`. Practical
  impact on *this* liquid top-300 backtest is small (1%-of-ADV budget ≫ neutralised
  weights, so the cap rarely binds), but the documented invariant is now false in
  one direction and the regression is untested.

## Round 6 re-check — check3 blocking finding resolved

- **Equal-magnitude flip (+0.4 → -0.4): FIXED.** `close_leg=-0.4` (free),
  `open_leg=-0.4` capped to -0.02/day → weights `[0.4, -0.02, -0.04, -0.06]`.
  Matches Claude's `0.4, -0.02, -0.04, -0.06`. Confirmed under `/tmp/verify_r6.py`.
- **Small long → big short (+0.06 → -0.4): FIXED.** Long closed fully on the flip
  day (`close_leg=-0.06` free), short opens capped → `[0.06, -0.02, -0.04]`. Matches
  Claude's `0.06, -0.02, -0.04`. Confirmed numerically.
- `test_sign_flip_equal_magnitude_capped` and `test_sign_flip_close_out_not_capped`
  assert these exact sequences and pass.

## Sigma change — consistent

- `_trailing_std` now receives `min_periods=min_obs` (`ceil(0.8*window)=48`) from
  `compute_residuals` (residual_reversion.py:253), aligning sigma's gap tolerance
  with the beta regression. Verified on 300-row series with injected gaps:
  `beta` non-NaN / `sigma` NaN days fell from **230** (full-window) to **49**
  (min_obs). The remaining 49 are the warm-up transition (residual NaN for the
  first `window` days), not gap starvation — consistent with
  `test_sigma_uses_min_obs_not_full_window` (passes). No look-ahead: sigma is a
  trailing inclusive std of residuals whose betas are themselves lagged.

## Answers to the check questions (unchanged-code items re-confirmed)

1. **OLS normal equations == `np.linalg.lstsq` on valid rows: YES.** Re-proved on
   300 rows with NaN gaps: 240 eligible windows, `max|coef err| = 1.02e-13`.
   Window still lagged: perturbing `y[180]` leaves `beta_mkt[180]` unchanged but
   moves `residual[180]`.
2. **ADV cap** — see blocking finding above for the residual regression; sign-flip
   and full-exit paths are now correct.
3. **`gold/06`, `gold/07` vs `strategies/universe.py`:** unchanged since check3 (the
   partial-window guards were round-5, already verified). `06:73-81` (COUNT=60
   guard ⟺ `rolling(60,min_periods=60).median().shift(1)`) and `07:72-78`
   (COUNT≥50 ⟺ `rolling(50,min_periods=50).mean()`) still match. Claude's live
   numbers — 300 names × 939 days, 0 NULL medians among members, SMA50 first
   non-NULL 2022-03-15 — are consistent with the SQL guards (`med_adv_60d IS NOT
   NULL` in `qualified`; SMA50 NULL until 50 prior rows).
4. **`residual_reversion_r5.md`:** internally consistent — baseline net
   -0.0803/Sharpe -0.363/net@2x -0.510 reproduce verbatim in the ablation
   "unconditioned" column; the caveat's gated `net@2x = -0.163` matches the table;
   walk-forward OOS net Sharpe -0.623 → DSR 0.000 coherent. Caveat explicitly says
   the gated comparison is "in-sample / full-period exploratory", "not evidence of
   an edge", cites gated net@2x -0.163 and DSR 0.000, and warns against live
   deployment without OOS validation. No unsupported numeric claims found (939 days,
   3 hold configs, 5 folds all match `run_residual_reversion.py`).

## Non-blocking notes

- `residual_reversion_r5.md` changelog row 1 (and the code comment) says
  "reductions were wrongly capped … opening beyond 0 is ADV-capped", which is
  inaccurate: same-side reductions are *still* capped (the blocking finding). The
  changelog overstates the fix's completeness.
- The caveat's DSR is computed on the gated `net` (1× cost) series while the quoted
  -0.163 is `net@2x`; both figures are individually accurate, just not the same
  series (pre-existing, cosmetic).
- The gated-ablation DSR uses `n_trials=3`, under-counting the breadth gate as a 4th
  trial; irrelevant since DSR is already 0.

## Checks run
```
$ python3 -m pytest -q tests/strategies tests/ml
76 passed, 34 warnings in 91.24s

$ python3 /tmp/verify_r6.py           # sign-flip re-check (both check3 cases)
A +0.4→-0.4 : [0.02 -0.02 -0.04 -0.06 -0.08 -0.1]   (close free, open capped)
B +0.06→-0.4: [0.02 0.04 0.06 -0.02 -0.04 -0.06]    (long closed free)

$ python3 /tmp/verify_reduce2.py       # same-side reduction regression (blocking)
build +0.4 then target 0.2: 0.4 0.38 0.36 0.34 0.32 0.30 0.28 0.26 0.24

$ python3 /tmp/verify_ols_sigma.py     # OLS==lstsq + lagged + sigma min_obs
OLS equivalence: 240 windows, max|coef err|=1.023e-13
lagged (no lookahead): beta_mkt[180] unchanged=True, residual moves=True
sigma starvation: new(min_obs)=49 days, old(full window)=230 days
```
===VERDICT END===
