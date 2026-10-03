===VERDICT START===
# VERDICT: strategy-round10 check8 — DeepSeek
**Status:** APPROVED
**Round:** 10 (check8)

Read-only re-check of commit `e7f91b5` (round 10) against the `CHECK-strategy-round9.md`
re-check section. Confirmed the check7 blocking finding is closed, traced the single ADV frame
through `run_one` → `run_backtest` → `cap_weight_changes_by_adv` → `compute_costs`, proved the
ffill is past-only (no look-ahead), confirmed the end-to-end exit-cost test asserts exact bps, and
verified the r9 report is internally consistent. Ran the full required suites (normal,
pyspark-hidden, cwd=test) and an independent `/tmp` proof. Nothing committed or pushed.

## Blocking findings

None. All four re-check items pass.

## 1. check7 finding is fixed — FIXED

check7's blocker was `backtest.py:345-346`: `run_backtest` rebuilt `adv_aligned =
adv.reindex(...).fillna(0.0)` for costs, so `compute_costs` (which does no ffill) charged a
dropped name's exit at `participation = 1.0` (~202 bps). Round 10 replaced that with:

```python
adv_aligned = adv.reindex(index=weights.index, columns=weights.columns).ffill().fillna(0.0)   # :343-344
weights = cap_weight_changes_by_adv(weights, adv_aligned, book_capital, params=cost_params)   # :345
...
adv_for_costs = adv_aligned.reindex(index=returns.index, columns=returns.columns).ffill().fillna(0.0)  # :353
costs = compute_costs(weights, adv_for_costs, ...)                                            # :355
```

The **SAME** ffill-then-zero frame now feeds both the cap and the costs. A dropped name whose ADV
turns NaN carries its last known ADV forward, so `compute_costs` at `backtest.py:211/215` sees a
non-zero ADV and charges true participation instead of 100 %. Independent proof (see Checks run):
exit cost = `0.00144000`, exactly the last-known-ADV value, vs `0.01616000` at 100 % participation.

## 2. No remaining zero-fill before costs; reindex/ffill order is past-only — PASS

- The only `fillna(0.0)` in the cost path is at `backtest.py:353`, applied **after** `.ffill()`, so
  it can only zero symbols that *never* had an ADV value. No `fillna(0)` precedes the cost ffill.
- The double ffill (`backtest.py:344` then `:353`) is redundant but harmless: `:344` fills the
  cap frame; `:353` reindexes to `returns.index` (which may extend past `weights.index`) and ffills
  again to carry the last known ADV onto extra dates. `ffill` is a forward fill of *past* values
  only — it never reads a future row, so no look-ahead is possible.
- Independent proof (`/tmp`): changing ADV on future dates (day 5+) leaves every cost on dates
  ≤ day 4 byte-identical → `past_invariant = True`. Reindexing onto a wider `returns.index` adds
  trailing NaN rows filled from past values only, never injects future volume.

## 3. End-to-end exit-cost test asserts exact bps — PASS

`tests/strategies/test_backtest.py::test_exit_cost_uses_last_known_adv_not_100pct_participation`
holds a name, drops it from the universe (ADV → NaN after drop), and asserts the exit-day
`turnover_cost` equals the analytically computed cost at last-known ADV (`pytest.approx(..., rel=1e-6)`)
and is `< 10%` of the 100 %-participation cost. This is an exact-bps assertion, not a loose
inequality, and it exercises `run_backtest` end-to-end (not `compute_costs` in isolation). The
companion `test_never_held_adv_name_charged_100pct_participation` pins the never-seen-ADV case to
202 bps, so both branches are covered. Both would FAIL on the pre-round-10 (check7) code, so the
regression is genuinely proven.

## 4. r9 report consistent — PASS

`strategies/results/residual_reversion_r9.md` (commit `6675526`) vs r8:

| metric | r8 | r9 | direction |
|---|---:|---:|---|
| net ann return | -0.0846 | -0.0804 | less negative (costs fell) |
| net Sharpe | -0.382 | -0.363 | up |
| net @2x Sharpe | -0.548 | -0.510 | up |
| OOS net Sharpe | -0.636 | -0.623 | up |
| OOS ann return | -0.2399 | -0.2351 | less negative |

- Matches Claude's rerun: r9 net −0.363 (r8 −0.382), OOS −0.623 (r8 −0.636). The fix now *changes*
  results (r8 was identical to r7 because the cost fix was a no-op; r9 differs as expected).
- Gross return unchanged (-0.0478), as it must be (pre-cost).
- Implied vol = ann-return/Sharpe = 0.2213 (gross) / 0.2215 (net) / 0.2216 (net@2x) — same across
  all three, so the numbers are arithmetically consistent.
- "What changed vs r8" renders `CHANGELOG[9]` (single-ADV-frame entry) verbatim.

## Read-only `.to_numpy()`/`.values` audit (round 9 check, re-verified for round 10)

Round 10 touched `backtest.py`, `run_residual_reversion.py`, and `test_backtest.py`. The only
in-place write into a `.to_numpy()`/`.values` result remains `backtest.py:84`
(`to_numpy(dtype=float, copy=True)` → `out[i] = ...` at `:124`), now a copy. `backtest.py:89`
(`adv_ff.fillna(0.0).to_numpy(dtype=float)`) is read-only. `ml/synthetic_data.py:104-106` writes a
freshly allocated `rng.normal(...)` array; `ml/evaluate.py:242` and all other sites are read-only.
No new pandas-3 read-only write sites were introduced.

## Non-blocking notes

- `compute_costs` docstring (`backtest.py:182`) still says "A name with unknown ADV is charged as
  100 % participation (conservative)". Accurate for *never-seen* names (still the fillna(0) branch),
  but it no longer describes dropped names whose last-known ADV is now forward-filled. A one-line
  clarification would remove the ambiguity the changelog otherwise resolves.
- The double ffill (`backtest.py:344` + `:353`) is redundant; collapsing to a single ffill (ffill
  the wider `returns.index` frame once, reuse for both cap and costs) would be marginally clearer.
  Not a defect.
- Round-number nomenclature remains off-by-one in the changelog (round-9 fixes → `CHANGELOG[8]`,
  round-10 → `CHANGELOG[9]`), but the result files and `_render` line up correctly (r8 renders
  `CHANGELOG[8]`, r9 renders `CHANGELOG[9]`). Historical quirk, not a blocker.

## Checks run

- `python3 -m pytest -q tests/strategies tests/ml` (repo root) → 86 passed, 34 warnings
- `python3 -m pytest -q tests/strategies tests/ml` with pyspark hidden via `/tmp/nopyspark/pyspark`
  ImportError stub (`PYTHONPATH=/tmp/nopyspark`) → 86 passed, 34 warnings
- `cd tests && python3 -m pytest -q strategies ml` → 86 passed, 34 warnings
- `python3 -m pytest -q tests/strategies/test_backtest.py -k "exit_cost or never_held or read_only"`
  → 4 passed (exit-cost-last-known-ADV, never-ADV-100 %, read-only-input, +1)
- Independent `/tmp` proof: exit cost = 0.00144000 (last-known $1e8 ADV) vs 0.01616000 (100 %
  participation); `uses_last_known_ADV=True`, `not_100pct=True`, `past_invariant=True` → no look-ahead
- `git status --short` → clean (no scratch files left; `.agents/dispatch.sh` untouched)
===VERDICT END===
