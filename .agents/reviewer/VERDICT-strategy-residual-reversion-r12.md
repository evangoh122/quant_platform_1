===VERDICT START===
Reviewer: Claude Sonnet subagent (stopgap for Codex, usage-limited)
Status: APPROVED

Scope: git diff origin/main...HEAD at 0894bde (75 files, +6490). Tests: `python3 -m pytest -q tests/strategies tests/ml` -> 94 passed, 0 failed.

Checks
1. Look-ahead: CLEAN.
   - Beta window ends at t-1 (residual_reversion.py:93-106, `_rolling_lagged_sum`; OLS at :150-175).
   - Universe at t uses a shift(1) median, history and recency (universe.py:62-71).
   - Fills[t] = desired[t-1] (backtest.py:41), then gross[t] = weights[t-1] * ret[t] (backtest.py:324). That is a conservative two-step lag with no same-bar fill.
   - Costs and the ADV cap use ffilled past ADV only (backtest.py:313-322).
   - s-score at t uses residual[t], which uses y[t] with betas fitted before t. That is fine, because the position is decided at the close of t and executed after t.
2. Masked breaks: no look-ahead, but a real P&L-bias caveat (non-blocking).
   - run_residual_reversion.py:208-214 builds valuation_returns as NaN only on masked days. Universe exits stay unmasked, so the round-11 exit-day P&L fix holds.
   - A held position's return on a masked day is dropped (the `.sum()` at backtest.py:324 skips NaN). The price level is continuous, so later returns are correct.
   - The dropped day is a real P&L event if the break is genuine (ticker reuse, delisting jump). Dropping it flatters P&L when the jump was adverse. The size is not quantified.
   - Required follow-up (documentation only): r10 should report the number of masked days that fall on days a position was held, and a sensitivity run with the masked-day return charged.
3. Statistics.
   - Purged walk-forward with embargo=10 and label_end = date+15 calendar days is sound (run_residual_reversion.py:422-433).
   - Only max_hold is selected on the training folds. Entry 2.5, exit 0.5, window 60 and lookback 5 are fixed.
   - n_trials=3 undercounts. About 12 rounds were iterated while looking at results, and the NARROW-regime ablation is a 4th configuration. The deflated Sharpe is therefore optimistic. The report must state this, and should preferably use a larger n_trials (e.g. >=12).
   - The OOS result is not strictly untouched. Earlier rounds saw OOS numbers, so a true holdout is absent.
   - The r10 results file in HEAD is a placeholder, so I could not verify any live numbers.
4. Costs: reasonable and conservative.
   - Commission 0.5 bps, half-spread 1.5 bps, slippage scaled by participation, borrow bucketed by ADV.
   - Exits are charged on actual notional with last-known ADV.
   - A 2x cost stress is reported (backtest.py:237-275, 330-334).
   - Borrow is a flat haircut, with no hard-to-borrow or recall modelling (acceptable at this ADV tier).

Findings (all non-blocking)
1. run_residual_reversion.py:193-214 and :566-568: masked-day P&L is dropped, not exit-priced. Quantify and disclose (see 2 above).
2. run_residual_reversion.py:433: n_trials=3 is understated. Disclose it, or raise it.
3. run_residual_reversion.py:421-427: there is no true untouched holdout. Disclose it.
4. residual_reversion.py:150: the loop is O(n_sym x n_dates) Python. This is a performance issue only.

Mutations (copies in /tmp/revmut_A..C, from git archive)
- A: remove the execution lag (backtest.py:41 `desired.fillna(0.0)`) -> FAILS test_backtest.py::test_signal_on_day_t_cannot_fill_on_day_t.
- B: include day t in the beta window (cs[idx+1]-cs[idx+1-window]) -> FAILS test_residual_reversion.py::test_perturbing_day_t_return_does_not_change_beta.
- C: ignore the mask (`if masked_breaks:` -> `if False:`) -> FAILS test_run_residual_reversion.py::test_masked_break_yields_nan_return.
All 3 mutants were killed. Tests were run with -x, so each mutant's first failure is shown.
===VERDICT END===
