# BUILD: strategy robustness round 4 (MiMo)

DeepSeek check3 (`.agents/deepseek/VERDICT-strategy-robustness-check3.md`): every section is now
computed, but three of them compute the WRONG quantity. Fix them; each needs a test that FAILS on the
current HEAD (prove it in /tmp).

1. **The rank IC target is the residual return.** `build_signals` must also return
   `res["residual"]` (OLS and PCA) under the key `"residual"`.
   - Feed the forward H-day SUM of residuals (t+1..t+H) into `compute_rank_ic`.
   - Rename the misleading `"residual_returns": sig.get("returns")`.
   - Test: a synthetic panel where total returns are dominated by a market factor and residuals carry
     the signal. The IC against residuals is high; against total returns it is near 0. The runner must
     use the former.
2. **An honest IC t-stat.** Use a Newey-West (HAC) standard error with lag = H-1 on the daily IC
   series, OR the non-overlapping subsample (every H-th date). Report which one, plus the effective n.
   Test: on an AR-correlated synthetic IC series, the reported t-stat is lower than the naive
   `mean/(std/sqrt(n))`, by roughly sqrt(H) for a pure overlap structure.
3. **Drop-top-3 is like-for-like.** Re-run the actual backtest (neutralisation, ADV cap, costs) on
   the validation window with the 3 names excluded from the eligible set. Compare that NET Sharpe with
   the full NET Sharpe on the same window.
   Test: with zero costs both paths agree with a hand computation; with costs, drop3 is charged costs.
4. **Sector exposure:** report the max |sector net exposure| per sector, plus the overall max, not
   the mean signed net.

Keep the guard test passing. Run:
- `python3 -m pytest -q tests/strategies tests/ml`;
- the same suite with pyspark hidden.

LF line endings only. Don't touch `.agents/dispatch.sh` or `strategies/results/`. Commit. Write
`.agents/mimo/VERDICT-strategy-robustness-round4.md`.
