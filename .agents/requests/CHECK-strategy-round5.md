# CHECK: strategy round 5 (DeepSeek)

Branch `slice/strategy-residual-reversion`. These are the round-5 fixes for CodeRabbit's findings on
PR #16, plus the results header. Read-only; scratch work goes in /tmp. Write
`.agents/deepseek/VERDICT-strategy-check3.md` (===VERDICT START/END===, Status).
Review the code changed since `b115443`.

1. **`strategies/residual_reversion.py`, validity mask.**
   - Do the OLS normal equations with per-row `n_valid` exactly match `np.linalg.lstsq` on only the
     valid rows? Prove it numerically on random data with gaps.
   - The window is still lagged (no day-t data in the day-t beta)?
   - `sigma` uses `rolling(window, min_periods=window)` on residuals that are NaN on gap days. Is
     that consistent, or does it starve signals? Classify it as blocking or not.
2. **`strategies/backtest.py`, ADV cap.**
   - Only increases are capped.
   - Is "increase" defined correctly when a position flips sign (long → short in one day)? The new
     short leg should be capped.
   - The forward-filled ADV uses only past data.
   - Prove a dropped name exits.
3. **`gold/06`, `gold/07`.**
   - The SQL guards match the pandas references in `strategies/universe.py`.
   - Live results: Claude rebuilt both tables. 300 names on each of 939 days, 0 NULL medians among
     members, SMA50 starts 2022-03-15. Do those numbers agree with the SQL?
4. **Results `strategies/results/residual_reversion_r4.md`.** Claude generated it live from WSL.
   - Is it internally consistent?
   - Is the changelog accurate?
   - Does the caveat say there is no edge (DSR 0, gated negative at 2× costs)?
   - Is there any claim the numbers don't support?

Run `python3 -m pytest -q tests/strategies tests/ml`.
