# BUILD: strategy round 5, CodeRabbit findings on PR #16 (MiMo)

Claude verified all four findings against the code. Fix all four. Each fix needs a test
that FAILS on the current code. Prove that by running the new test against `git stash`-free
copies in /tmp, and paste the outputs in the verdict.

## 1. [Major] `strategies/residual_reversion.py:98-135`: NaN returns counted as zeros
`_rolling_lagged_sum` calls `np.nan_to_num`, and `_rolling_residuals_one_symbol` uses
`n = float(window)`. A symbol with 30 valid days in a 60-day window is fitted as if it had
30 zero-return days. This breaks the round-2 rule "missing returns stay NaN, never 0".

Fix:
- Use a per-row validity mask: `valid = isfinite(y) & isfinite(m) & isfinite(f)`.
- Zero the invalid rows in ALL inputs, so the cross-products use the same rows.
- Get `n[t]` as the rolling lagged sum of `valid`.
- Set the output to NaN where `n[t] < min_obs`, with a new param `min_obs`, default
  `ceil(0.8 * window)`.
- Build the OLS from these masked sums, with per-row n.

Test: a series with gaps must match `np.linalg.lstsq` on only the valid rows in the window.

## 2. [Major] `strategies/backtest.py:63-96` (and the runner): positions freeze when ADV is 0
ADV is pivoted only for universe members, then `fillna(0)`. When a held name leaves the
universe, its target becomes 0 but `cap = 0.01 * 0 = 0`. So the exit is capped to zero
change and the position is held forever.

Fix:
- The cap must never block a reduction toward 0.
- Use the last known ADV for that symbol (forward-fill ADV for non-members, from data
  available at t, no look-ahead).
- If no ADV is known, allow full liquidation.
- Increases stay capped (0 ADV → no increase).

Test: a name held, then dropped from the universe with NaN ADV, goes to 0 weight within a
bounded number of days, never stays frozen.

## 3. [Major] `gold/06_gold_tradable_universe.sql:70-74`: partial-window median
`PERCENTILE` ignores NULL grid rows, so a 60-session window with 5 bars still gets ranked.
The pandas reference uses `min_periods=adv_window`.

Fix: compute `COUNT(dollar_volume)` over the same 60-row window, and set `med_adv_60d` to NULL
unless the count is 60. Membership requires a non-null median.

Keep the round-4 `WHEN NOT MATCHED BY SOURCE THEN DELETE` and the history gate.

## 4. [Minor] `gold/07_gold_regime_features.sql:~70,101-105`: partial SMA50
Make the SMA NULL when `COUNT(*) OVER (same window) < 50`. The CASE then labels those
dates MIXED.

## Then
- Run `python3 -m pytest -q tests/strategies tests/ml`, plus the pyspark-free check:
  `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/strategies`.
  Create `/tmp/nopyspark/sitecustomize.py` that sets `sys.modules[m]=None` for pyspark,
  pyspark.sql, pyspark.sql.functions and pyspark.sql.types.
- You cannot reach Databricks from Windows. Do NOT write results files. Claude will
  rebuild the gold tables and rerun the backtest from WSL as round 5 results (r4).
- LF line endings. Don't touch `.agents/dispatch.sh`. Commit. Write
  `.agents/mimo/VERDICT-strategy-round5.md`.
