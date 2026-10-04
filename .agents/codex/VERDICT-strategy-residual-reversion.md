# VERDICT: strategy round 1 (item A) + ML pandas fix (item B) — Codex

## ITEM A — CHANGES_REQUESTED

Material findings:

1. **Point-in-time universe still has look-ahead.**  
   [gold/06_gold_tradable_universe.sql](/home/jianj/code/qp1-strat2/gold/06_gold_tradable_universe.sql:36) constructs candidate dates from each symbol’s own bars, so membership on date `t` implicitly requires knowing that the symbol traded on `t`. Additionally, [lines 59–62](/home/jianj/code/qp1-strat2/gold/06_gold_tradable_universe.sql:59) count the previous five observations for that symbol, not the previous five market sessions. A symbol missing intervening sessions can therefore pass the recency test. The universe should be formed from a market calendar crossed with symbols and use only observations strictly before `t`.

2. **Historical industry factors depend on the full-period symbol set.**  
   [run_residual_reversion.py:78](/home/jianj/code/qp1-strat2/strategies/run_residual_reversion.py:78) fetches every symbol that appears in the universe at any point; [run_residual_reversion.py:142](/home/jianj/code/qp1-strat2/strategies/run_residual_reversion.py:142) creates one full-period wide frame. Missing observations—including periods before a symbol existed—become zero returns at [residual_reversion.py:57](/home/jianj/code/qp1-strat2/strategies/residual_reversion.py:57), while [residual_reversion.py:73](/home/jianj/code/qp1-strat2/strategies/residual_reversion.py:73) uses a fixed full-sample industry membership count. Adding a future-listed symbol can therefore alter earlier industry factors and residuals. Industry factors need date-specific eligible membership and must not treat unavailable returns as zero.

3. **The ADV cap does not constrain simulated execution.**  
   [backtest.py:138](/home/jianj/code/qp1-strat2/strategies/backtest.py:138) caps the notional only while calculating transaction cost. The original uncapped weights still generate P&L at [backtest.py:260](/home/jianj/code/qp1-strat2/strategies/backtest.py:260) and full-position borrow at [backtest.py:151](/home/jianj/code/qp1-strat2/strategies/backtest.py:151). Thus oversized or zero-ADV orders can earn returns even though their transaction cost is calculated on a smaller—or zero—notional. Apply the cap to actual executed weight changes and carry the resulting positions forward.

4. **The positive breadth-gated result is insufficiently caveated.**  
   [residual_reversion_r1.md:26](/home/jianj/code/qp1-strat2/strategies/results/residual_reversion_r1.md:26) reports gated net Sharpe `+0.073`, but the report provides no warning that it is an in-sample/full-period ablation, fails at 2× costs (`-0.421`), and has no independently significant evidence. The reported DSR is zero at [line 40](/home/jianj/code/qp1-strat2/strategies/results/residual_reversion_r1.md:40). The write-up should explicitly state that the apparent gated improvement is exploratory and not evidence of an edge.

Other checks:

- Regression betas use `[t-window, t-1]` correctly at [residual_reversion.py:125](/home/jianj/code/qp1-strat2/strategies/residual_reversion.py:125).
- The s-score uses information available at day `t` close and is subsequently lagged.
- The breadth gate is based on date-`t` close data and is execution-lagged at [backtest.py:35](/home/jianj/code/qp1-strat2/strategies/backtest.py:35).
- Walk-forward parameter selection occurs on training indices only at [run_residual_reversion.py:232](/home/jianj/code/qp1-strat2/strategies/run_residual_reversion.py:232), with purging and embargo requested at [line 226](/home/jianj/code/qp1-strat2/strategies/run_residual_reversion.py:226). The three stated hold configurations match the three selection candidates.
- Gross, net, and 2×-cost results are reported; short borrow is charged only to negative weights.
- The additions to `pipelines/run_silver_gold.py` and the new schema sections in `docs/DATA_SCHEMAS.md` are additive and safe. The documentation also adds a missing `processed_ts` entry to the preceding schema, which is documentation-only.

Requested test run: **21 passed**.

## ITEM B — APPROVED

Commit `84b2458` is correct and behavior-preserving.

[ml/features.py:580](/home/jianj/code/qp1-ml/ml/features.py:580) converts only `residualise_cols` to numeric float before floating-point residuals are assigned at [line 603](/home/jianj/code/qp1-ml/ml/features.py:603). This makes pandas 3’s dtype requirements explicit while matching pandas 2’s previous implicit upcast. Market-wide and excluded nonnumeric columns remain untouched.

Targeted ML hardening tests: **21 passed**.

