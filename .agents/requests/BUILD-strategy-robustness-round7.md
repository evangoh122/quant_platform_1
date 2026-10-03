# BUILD: strategy robustness round 7 (MiMo)

DeepSeek check6 (`.agents/deepseek/VERDICT-strategy-robustness-check6.md`) found a NEW blocking bug.
Codex's three findings are confirmed fixed.

## 1. [Blocking] PCA residual written to the wrong column
In `strategies/residual_reversion.py:~304,368,390`, `residual` is keyed by the FULL symbol list, but
the loop writes `residual.iloc[t, j]` with `j` = the position within `valid_syms` (a subset). Whenever
a symbol is excluded from the fit, every later residual, `sigma` and `s_score` shifts to the wrong
symbol. That happens in the live path because the point-in-time universe mask creates NaN gaps.

Fix:
- Write by label: `residual.loc[dates[t], sym] = ...`. Audit EVERY other positional write in
  `compute_pca_residuals` and the PCA path the same way.
- Test: an 8-symbol panel with a NaN in S00 inside the t window. S00's residual at t must be NaN, and
  every other symbol's residual must equal an independent per-symbol computation (projection onto the
  fitted factors). Prove in /tmp that the test fails on the current HEAD.
- Also add a property test: with random NaN gaps, `residual[sym]` depends only on `sym`'s own returns
  and the fitted factors. Permuting the column order of the input permutes the output identically.

## 2. Surface drop-top-3 failures (non-blocking, but do it)
At `strategies/run_residual_reversion.py:~618`, `except Exception: pass` silently renders
drop3 == full. Record the failure in the report row ("drop3 failed: <ExcType>") and exclude it from
gates. Test it.

## 3. Docstring honesty
`remove_top_pnl_contributors` (`strategies/robustness.py:~212`) says "allocated costs" but sums gross.
Either allocate costs, or fix the docstring and the report label to say "gross P&L ranking".

## Then
- Make the PCA fit tolerance a documented choice. Either apply `min_obs` like OLS, or state in the
  report that PCA needs a full window.
- Run `python3 -m pytest -q tests/strategies tests/ml`, and the same suite with pyspark hidden.
- LF line endings only. Don't touch `.agents/dispatch.sh` or `strategies/results/`. Leave no scratch
  files. Commit with a DESCRIPTIVE message. Write `.agents/mimo/VERDICT-strategy-robustness-round7.md`.
