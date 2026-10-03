# BUILD: strategy robustness round 5 (MiMo)

DeepSeek check4 (`.agents/deepseek/VERDICT-strategy-robustness-check4.md`), two blocking findings:

1. **Drop-top-3 picks names using residual returns, which round 4 broke.** In
   `strategies/run_residual_reversion.py:~575-588`, the per-fold selection uses
   `hold_vr["residual_returns"]`, but realised P&L is `lagged_weight × tradeable_returns`. Pick the
   top-3 names by REALISED P&L, using the same returns `run_one` trades (`sig["returns"]`), over the
   TRAIN window only. Keep the residuals ONLY for the rank IC. Store the two under distinct keys
   (`trade_returns`, `residual`), so they can't be confused again. Make `remove_top_pnl_contributors`
   and the per-fold path share one helper.
   Test: in a market-dominated synthetic panel with distinct betas, the top-3 by realised P&L
   differs from the top-3 by residual P&L. Assert the dropped names equal the realised-P&L set.
2. **Rank IC disclosure.** The Rank IC table must state the method (Newey-West HAC, lag = H-1) and
   show `effective_n` next to `n`. Extend the guard test to assert both appear.

Each new test must FAIL on the current HEAD (prove it in /tmp). Run:
- `python3 -m pytest -q tests/strategies tests/ml`;
- the same suite with pyspark hidden.

LF line endings only. Don't touch `.agents/dispatch.sh` or `strategies/results/`. Commit with a
DESCRIPTIVE message (not "fix:"). Write `.agents/mimo/VERDICT-strategy-robustness-round5.md`.
