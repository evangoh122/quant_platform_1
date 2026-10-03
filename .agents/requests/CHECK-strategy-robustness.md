# CHECK: strategy robustness + PCA lane (DeepSeek)

Branch `slice/strategy-robustness`. Spec: `.agents/requests/BUILD-strategy-robustness.md` (its
"DeepSeek must check" list is mandatory). Implementation: commit 9df2030. Round 7 of #16 has been
merged in since. Read-only; scratch work goes in /tmp. Write
`.agents/deepseek/VERDICT-strategy-robustness.md` (===VERDICT START/END===, Status).

Hardest first:
1. **Point-in-time in PCA.**
   - Factor loadings and the covariance for day t use only data before t.
   - Prove it by perturbing day t and later, and showing the loadings at t are unchanged.
   - Shrinkage (Ledoit-Wolf) is fit only on the lagged window.
   - The sign/rotation indeterminacy of PCA must not leak or flip signals between days.
2. **Universe-size look-ahead.** Top-200/300/500 are built from daily bars point-in-time, with the
   same rules as `gold/06` (60-session full-window median, recency 5, history ≥ 252 own sessions,
   ranks from data before t). Top-300 from this path should reproduce `gold_tradable_universe`
   membership. Is there a test of that equivalence on synthetic data?
3. **Trial counting.** Every variant evaluated (cost multiples ×3, universes ×3, ±20% perturbations,
   factor models, hold configs) counts toward `n_trials` for the deflated Sharpe. Is anything
   evaluated but not counted?
4. **Cost stress.** The cost is scaled exactly once (not double-applied), and borrow is included.
5. **Other measures.**
   - Top-3 contributor removal: computed on P&L, out-of-sample.
   - Per-fold Sharpe: on the purged folds.
   - Rank IC: the s-score at t vs the residual return over t+1..t+H, no overlap leakage.
6. **Config alignment.** `strategies/config.yaml` no longer leads with pairs or the basket, and the
   dead-key test is real.
7. **Tests.** They fail on the old code. They pass with pyspark hidden. They don't depend on the
   ambient env.

Run:
- `python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml`;
- the same suite with pyspark hidden, via a sitecustomize that sets `sys.modules[m]=None` for
  pyspark, pyspark.sql, pyspark.sql.functions and pyspark.sql.types.

## Re-check after round 2 (this run)
MiMo round 2 (commit 0e972e0) addresses your four blocking findings. See
`.agents/requests/BUILD-strategy-robustness-round2.md`. Strategy round 8 from #16 has been merged in
since (executed-notional costs, dense-grid `universe.py`, z-score guard).

Re-verify every item with proofs:
- **Top-500 is real.** It comes from a full bronze panel, and it differs from top-300.
- **Parity.** Top-300 from the pandas screen matches the SQL semantics, including a missing session.
- **Drop-top-3** executes, uses training-window P&L, and the dropped names hold zero weight.
- **Report tables.** Every required table, plus the IS/OOS columns and the OOS-ratio gate, is present
  and computed.
- **Config.** The keys are really consumed, and the cost params come from config in the baseline.
- **Honest trial count.** No counted variant is a silent duplicate.

Also check that merging round 8 didn't break the robustness code paths: costs on the executed
notional inside the cost-stress variants, and the dense-grid screen inside `fetch_data`.
Write `.agents/deepseek/VERDICT-strategy-robustness-check2.md`.

## Re-check after round 3 (this run)
MiMo round 3 (commit 499b502) addresses your check2 findings (see
`.agents/requests/BUILD-strategy-robustness-round3.md`):
- real rank IC;
- capacity;
- beta and sector exposures;
- drop-top-3 chosen per fold on TRAIN P&L;
- a guard test against placeholders and unused `compute_*` functions.

Verify each one, with proofs:
- rank IC alignment, no overlap leakage, and an honest t-stat;
- capacity numbers sane vs ADV;
- exposures use the real betas and taxonomy;
- drop-top uses only train-window P&L;
- the guard test FAILS on 0e972e0.

Also hunt for any OTHER report section that looks computed but isn't.
Write `.agents/deepseek/VERDICT-strategy-robustness-check3.md`.

## Re-check after round 4 (this run)
MiMo round 4 addresses your check3 findings (see `.agents/requests/BUILD-strategy-robustness-round4.md`):
- the rank IC target is the forward residual sum;
- the t-stat is HAC (Newey-West) or non-overlapping;
- drop-top-3 re-runs the full backtest (neutralise, cap, costs) → net vs net;
- sector exposure is reported as the max |net|.

Verify each one, with proofs (synthetic factor-dominated panel; AR-correlated IC series; zero-cost
hand check). Hunt for any remaining miscomputed quantity in the report.
Write `.agents/deepseek/VERDICT-strategy-robustness-check4.md`.

## Re-check after round 5 (this run)
MiMo round 5 (commit cc2f9e0):
- per-fold drop-top-3 picks names by REALISED P&L (`trade_returns`) on the train window;
- rank IC uses the residuals under a distinct key;
- the Rank IC table shows the method (Newey-West HAC, lag H-1) and `effective_n`.

Verify both check4 findings with proofs. Then do a final full pass over EVERY report quantity: is
each one computed, on the right quantity, without look-ahead, and like-for-like? If everything
passes, say so explicitly. Write `.agents/deepseek/VERDICT-strategy-robustness-check5.md`.

## Re-check after round 6 (this run)
Codex's review (`.agents/codex/VERDICT-strategy-robustness.md`) found:
- PCA loadings depending on day-t availability (look-ahead);
- an ineffective unused-`compute_*` guard;
- no PCA K validation.

MiMo round 6 claims to fix all three. Verify with proofs:
- a day-t NaN or huge value leaves the day-t loadings identical;
- the AST guard fails on an added unused import;
- K outside [10, 15] raises.

Re-run the full pass on the report quantities. Write
`.agents/deepseek/VERDICT-strategy-robustness-check6.md`.

## Re-check after round 7 (this run)
MiMo round 7 (commit 459eb4d) fixes your check6 PCA column misalignment, surfaces drop-top-3
failures, and corrects the docstring. Claude's independent probe: on a 14-symbol panel with a NaN in
S00 inside the window, S00's residual at t=100 is NaN, and the residuals are invariant to permuting
the column order.

Verify with your own probe:
- per-symbol alignment against an independent projection;
- audit every positional write in the PCA path;
- drop3 failure surfacing;
- the PCA fit-tolerance choice is documented.

Full pass on the report quantities. Write `.agents/deepseek/VERDICT-strategy-robustness-check7.md`.
