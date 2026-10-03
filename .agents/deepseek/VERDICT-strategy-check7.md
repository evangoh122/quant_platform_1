===VERDICT START===
# VERDICT: strategy-round9 check7 — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 9 (check7)

Read-only re-check of commit `e3d413b` against the `CHECK-strategy-round9.md` brief. Audited every
`.to_numpy()`/`.values` write site, traced the ADV frame through `run_one` → `run_backtest` →
`cap_weight_changes_by_adv` → `compute_costs`, ran the full required suites (normal, pyspark-hidden,
cwd=test), and produced an independent `/tmp` proof of the cost path. Nothing committed or pushed.

## Blocking findings

- **[strategies/backtest.py:345-346] ADV fix does not reach the cost path — the CodeRabbit Major
  issue is not actually fixed.** The round-9 fix removed `fillna(0)` from `run_one`
  (`run_residual_reversion.py:196`) and from the cap input (`backtest.py:339`), but `run_backtest`
  then **re-zero-fills** the frame for costs:
  ```python
  adv_aligned = adv.reindex(index=returns.index, columns=returns.columns)  # :345
  adv_aligned = adv_aligned.fillna(0.0)                                    # :346
  costs = compute_costs(weights, adv_aligned, ...)                         # :348
  ```
  `compute_costs` does no forward-fill; at `backtest.py:211/215` a zero/NaN ADV yields
  `participation = 1.0` (100 %), so the slippage term is `slippage_bps * (1.0 / 0.01) = 200 bps`.
  A dropped name's exit is therefore **still costed at 100 % participation**, contradicting both the
  round-9 changelog ("exits use last known ADV instead of 100 % participation") and the
  BUILD/CHECK requirement "the SAME frame feeds both the cap and the costs".
  → Independent proof: a name held then dropped (ADV NaN after drop) exits with `turnover_cost =
  0.00404` (202 bps on $2M notional), not `~0.00012` (6 bps, last-known $1e8 ADV). See Checks run.

- **[tests/strategies/test_backtest.py] The BUILD-required test was never added.** The BUILD brief
  mandates "Test: a name held, then dropped from the universe. The exit cost uses its last known ADV,
  not 100 % participation." The only new test is `test_cap_weight_changes_with_read_only_input`. No
  test asserts the exit-cost-vs-last-known-ADV behaviour, so the regression the fix claims to close
  is unproven — and, per the finding above, would currently fail.

## Checks 1–4 (detail)

1. **Read-only `.to_numpy()`/`.values` audit — PASS.** The only in-place write into a
   `.to_numpy()`/`.values` result in `strategies/`, `ml/`, `tests/` is `backtest.py:84`
   (`out[i] = ...`), now `to_numpy(dtype=float, copy=True)`. All other sites are read-only (np
   algebra, `np.linalg.lstsq`, iteration, function args) or write to a freshly allocated array
   (`ml/synthetic_data.py:104-106` writes `X = rng.normal(...)`, not a `.values` view). The new
   read-only test (`setflags(write=False)`) is a faithful pandas-3 CoW reproduction on pandas 2.

2. **ADV forward-fill / SAME-frame — FAIL (blocking).** The cap input is forward-filled inside
   `cap_weight_changes_by_adv` (`backtest.py:88-89`), but the cost frame is separately zero-filled
   (`backtest.py:345-346`). The same frame does **not** feed both. Zero-fill-only-for-never-seen is
   not achieved for costs: a name with prior ADV that leaves the universe still costs at 100 %.

3. **r8 == r7 plausibility — CONFIRMED, and the fix is the reason.** The cost input is
   byte-identical pre/post round 9: `fillna(0)` applied to `fillna(0)`-ed values equals
   `fillna(0)` applied to NaNs — both yield the same zero frame, so `compute_costs` is unchanged.
   The cap's new `ffill` only changes output for a name that is in-universe with NaN ADV *and* a
   prior known ADV; that never occurs because `med_adv_60d` is NULL only for a name's first 60
   sessions (round-4 rule), i.e. NaN ADV has no prior non-NaN to fill from. So the old zero-fill
   never "bit" in a way the fix alters → r8 == r7 (−0.382 / −0.636 / DSR 0.000) is fully explained
   by the fix being a no-op. Crucially, the tests do **not** prove the intended behaviour: nothing
   asserts the last-known-ADV exit cost.

4. **Test-path fixes from any cwd — PASS.** `tests/strategies/test_universe.py:238` and
   `tests/lakebase/test_migrations.py:140` now resolve via `Path(__file__).resolve().parents[2]`.
   `cd tests && pytest -q strategies ml` → 84 passed.

## Non-blocking notes

- `compute_costs` docstring (`backtest.py:180-182`) still claims "A name with unknown ADV is charged
  as 100 % participation (conservative)" — accurate, but it now conflicts with the changelog's
  "exits use last known ADV". The intended (unimplemented) behaviour would need this doc updated.
- `.agents/mimo/VERDICT-strategy-round9.md` (§2, "The second ADV alignment … retains `fillna(0.0)`
  since `compute_costs` treats NaN/0 identically (100 % participation)") confuses "NaN and 0 both
  produce 100 % participation" with "the forward-fill goal is met". They are not equivalent: the
  whole point of the fix was to forward-fill so participation is *not* 100 %. This is the crux of
  the incompleteness.

## Checks run

- `python3 -m pytest -q tests/strategies tests/ml` (repo root) → 84 passed, 34 warnings
- `python3 -m pytest -q tests/strategies tests/ml` with `PYSPARK_PYTHON=` → 84 passed, 34 warnings
- pyspark genuinely hidden via `sys.meta_path` ImportError blocker → 84 passed, 34 warnings
- `cd tests && python3 -m pytest -q strategies ml` → 84 passed, 34 warnings
- `/tmp/verify_adv_round9.py` (independent, deleted after): held name 0.2 → dropped, exit
  `turnover_cost == 0.00404` (100 % participation) vs expected `~0.00012` had last-known $1e8 ADV
  been used → `match=False` for the round-9 cost claim
- `grep` for `.to_numpy(`/`.values` in `strategies/`, `ml/`, `tests/` → single write site confirmed
- `git diff r7 vs r8` result files → identical to 3 decimals (net −0.382, OOS −0.636, DSR 0.000)
===VERDICT END===
