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
