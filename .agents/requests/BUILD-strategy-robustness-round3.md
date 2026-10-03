# BUILD: strategy robustness round 3 (MiMo)

DeepSeek check2 (`.agents/deepseek/VERDICT-strategy-robustness-check2.md`): 4 report measures are
still headings with nothing computed behind them. This is the second round with that pattern. This
round also adds a guard test so it can't happen again.

1. **Rank IC is real.** Call `compute_rank_ic` in the runner for the baseline (and per factor model):
   the s-score at t vs the residual return over t+1..t+H, for H in the hold candidates. Report the
   mean IC, the IC t-stat (Newey-West or the non-overlapping-sample count) and the hit rate. Remove the
   "--rank-ic" placeholder text.
2. **Capacity is real.** Call `compute_capacity`. Report the median and 5th-percentile capacity in
   dollars, at the configured ADV participation, and the book size at which the cap binds on more than
   X% of trades. State X.
3. **Exposures are complete.** Pass the real rolling betas (`beta_mkt` from the residual model) and
   the industry labels (`config/tickers.yaml` taxonomy) into `compute_exposures`. Report the
   max/mean |beta exposure|, the max/mean |dollar exposure| and the max |sector net| per sector.
4. **Drop-top-3 uses training-window P&L only.** Per walk-forward fold:
   - choose the top-3 names by P&L in that fold's TRAIN window;
   - drop them;
   - evaluate on that fold's VALIDATION window.

   Report the OOS Sharpe with and without them.

## Guard test (mandatory)
`test_report_has_no_placeholders`: render the report from a synthetic run and assert:
- no "Run with", "TODO", "placeholder", "N/A" (except where a gate is legitimately inapplicable,
  with a stated reason) or "nan" in any required table;
- every required table has at least one numeric row;
- every `compute_*` function imported by the runner is actually called. Spy on them, or assert the
  module has no unused imports from `strategies.robustness`.

Prove the guard FAILS on the current HEAD (/tmp).

Run:
- `python3 -m pytest -q tests/strategies tests/ml`;
- the same suite with pyspark hidden (`PYTHONPATH=/tmp/nopyspark`).

Every new test must fail on the current HEAD. LF line endings only. Don't touch
`.agents/dispatch.sh` or `strategies/results/`. Commit. Write
`.agents/mimo/VERDICT-strategy-robustness-round3.md`.
