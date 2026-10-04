===VERDICT START===
# VERDICT: strategy-residual-reversion round 7 re-check — DeepSeek
**Status:** APPROVED
**Round:** 7

Re-verified the round-7 fixes (commits `d6c5f70` same-side reduction + `c7ae640` property test)
on `slice/strategy-residual-reversion` against my check3 and check4 blocking findings, plus the
sigma change and the r6 results. All scratch work under `/tmp`; nothing committed or pushed.

## Blocking findings

None. Both prior blocking findings are resolved and the property test now covers them.

## check3 blocking finding (sign-flip ADV cap) — RESOLVED, still correct

- **Equal-magnitude flip (+0.4 → -0.4):** `close_leg=-0.4` free, `open_leg=-0.4` capped →
  `[0.02, -0.02, -0.04, -0.06, -0.08, -0.10]` (day 0 is the build from 0; the flip day is -0.02
  then -0.04 …). Matches Claude's `0.4, -0.02, -0.04, -0.06`. Confirmed numerically.
- **Small long → big short (+0.06 → -0.4):** `[0.02, 0.04, 0.06, -0.02, -0.04, -0.06]` — the long
  is fully closed on the flip day (close leg -0.06 free), the new short opens capped. Matches
  Claude's `0.06, -0.02, -0.04`.

## check4 blocking finding (same-side partial reduction) — RESOLVED

- `+0.4 → +0.2` now lands in **one day**: the round-7 `close_leg` routes same-side reductions
  (`|cur| < |prev|`) into the free leg (`np.where(np.abs(cur) < np.abs(prev), dw, 0.0)`). Verified:
  build to +0.4 over 20 days, day 20 = **0.2** exactly (round-6 code gave 0.38/0.36/… throttled).
- Full exit still free: `+0.3 → 0` gives `[0.02, 0.04, 0.0, 0.0, 0.0]`.

## Round 7 re-check — does the property test fully specify the cap semantics?

**Mostly yes, with one gap.** I re-ran the seeded (42) 500-sequence property test against all three
versions of `cap_weight_changes_by_adv`:

| version | violations |
|---|---:|
| round-5 `75e0e7d` | 7546 (flip-not-closed / flip-exceeds-cap) |
| round-6 `1d956ea` | 170 (reduction-not-free) |
| round-7 `HEAD` | 0 |

- The property test **does** catch the round-6 same-side reduction regression — invariant (b)
  ("target between 0 and prev → out == target") fires 170 times. A concrete case:
  `trial=1 S0 d11: prev=+0.06, target=+0.0284, out=+0.04` (reduction throttled at the cap instead
  of landing free). So the invariants stop the ping-pong in **both** directions, not just the flip.
- **Gap:** invariant (d) compares increases against a *fixed* `cap = 0.02` derived from the
  constant `adv_val`, so the property test does **not** enforce ADV-proportionality or the docstring
  clause "zero-ADV names cannot accumulate new positions". Constructed counterexample: an
  implementation that caps every increase at a fixed 0.02 (ignoring ADV) passes all 500 sequences
  with 0 violations, yet on a leading-NaN-ADV day (ADV → 0) it opens `+0.02` on a name with zero
  ADV — a docstring violation the property test misses. This is covered by the explicit unit test
  `test_adv_cap_constrains_execution` (zero-ADV name D never trades), so it does not block.
- **Discrepancy flagged:** MiMo's round-7 verdict states "Round-6 code: 0 violations" and reasons
  that the unit test is what catches the regression "specifically". That is **incorrect** — the
  property test itself reports 170 violations on round-6 code (invariant b). The property test is a
  stronger spec than MiMo credited. (No impact on code correctness.)

## Sigma change — consistent

`_trailing_std` now takes `min_periods=min_obs` (`ceil(0.8*window)=48`). On a 300-row series with
~10% gaps: sigma starvation (beta non-NaN, sigma NaN) falls from **180** (old `min_periods=window`)
to **0** (new `min_obs`). No look-ahead: sigma is a trailing inclusive std of residuals whose betas
are themselves lagged. `test_sigma_uses_min_obs_not_full_window` passes.

## Answers to the check questions (unchanged-code items re-confirmed)

1. **OLS normal equations == `np.linalg.lstsq` on valid rows: YES.** Random data with NaN gaps in
   `y`,`m`,`f` (300 rows): 196 eligible windows, `max|coef err| = 1.78e-15`. The zeroed
   cross-products with per-window `n_valid` reproduce `lstsq` exactly.
2. **Window still lagged: YES.** Perturbing `y[180]` leaves `beta_mkt[180]`/`beta_ind[180]`
   unchanged but moves `residual[180]`.
3. **`gold/06`, `gold/07` vs `strategies/universe.py`:** unchanged since check3 (last touched in
   round-5 `75e0e7d`; not in the round 6/7 diffs). The partial-window guards already verified:
   `06` `COUNT(dollar_volume)=60` guard ⟺ `rolling(60,min_periods=60).median().shift(1)`; `07`
   `COUNT(rsp_spy_ratio)>=50` ⟺ `rolling(50,min_periods=50).mean()`.
4. **`strategies/results/residual_reversion_r6.md`:** internally consistent — baseline `net`
   -0.0803 / Sharpe -0.363 / net@2x -0.510 reproduce verbatim in the ablation "unconditioned"
   column; the caveat's gated `net@2x = -0.163` matches the table; walk-forward OOS Sharpe -0.623 →
   DSR 0.000 coherent. **r6 numbers equal r5** (the round-7 fix is behaviour-neutral for the liquid
   top-300 universe). Changelog (1 row, same-side reduction) accurately reflects the `d6c5f70`
   change. The caveat is honest: it says the gated comparison is "in-sample / full-period
   exploratory", "not evidence of an edge", quotes gated net@2x **-0.163** and DSR **0.000**, and
   warns against live deployment without OOS validation. No unsupported numeric claims found.

## Non-blocking notes

- MiMo's round-7 verdict claims the property test does not fail on round-6 code; my reproduction
  shows it fails with 170 violations. The property test is complete for the reduction/flip/increase
  semantics; only ADV-proportionality (zero-ADV accumulation) is outside its fixed-`cap` checks, and
  that is covered by `test_adv_cap_constrains_execution`.
- The caveat's DSR is computed on the gated `net` (1×) series while the quoted -0.163 is `net@2x`;
  both figures are individually accurate (pre-existing, cosmetic, unchanged from check4).

## Checks run

```
$ python3 -m pytest -q tests/strategies tests/ml
78 passed, 34 warnings in 94.80s

$ python3 /tmp/verify_ds7.py            # OLS==lstsq, lagged, ADV-cap cases
OLS==lstsq: checked 196 windows, max|coef err|=1.776e-15
flip +0.4->-0.4: [ 0.02 -0.02 -0.04 -0.06 -0.08 -0.1 ]
small long +0.06->-0.4: [ 0.02  0.04  0.06 -0.02 -0.04 -0.06]
same-side reduction +0.4->+0.2: [0.38 0.4  0.2  0.2  0.2  0.2 ]
exit +0.3->0: [0.02 0.04 0.   0.   0.  ]

$ python3 /tmp/verify_sigma.py          # lagged + sigma min_obs
lagged (clean): beta_mkt[180] unchanged=True, residual moves=True
sigma starvation: old(full window)=180, new(min_obs)=0

$ python3 /tmp/verify_prop.py           # property test on 3 versions
round5 75e0e7d: 7546 violations
round6 1d956ea: 170 violations   (red-not-free)
round7 HEAD:    0 violations

$ python3 /tmp/verify_gap.py            # property-test gap (ADV-proportionality)
buggy_cap (fixed 0.02, ignores ADV) property violations: 0
zero-ADV day0 target=+1.0 -> buggy_cap out = 0.02 (docstring says must be 0)
```
===VERDICT END===
