===CODEX VERDICT START===
APPROVED

- DeepSeek check-7: APPROVED.
- Standard suite: 178 passed, 34 warnings.
- Suite with pyspark hidden: 178 passed, 34 warnings.
- Independent `/tmp` proofs passed:
  - PCA lagging, deterministic orientation, NaN-gap label alignment, independent projection, and column-permutation invariance.
  - Top-500 sourced from Bronze; top-300 dense-calendar parity including a missing session.
  - 72 executed variants equals 72 distinct fingerprints despite duplicate-inducing configuration entries.
  - Transaction and borrow costs scale exactly once; gross P&L is unchanged.
  - Rank IC uses forward residual sums; overlapping-data |HAC t| was 19.07 versus |naive t| 31.25.
  - Per-fold drop-top-3 uses training-window realised P&L and compares net OOS results.
  - Placeholder and unused-import guards detect the constructed mutations.
- Previous Codex findings are resolved: day-t PCA eligibility, unused-import guard, and K validation in [10,15].
- Report language correctly treats gates as research PASS/FAIL/N/A outcomes and expressly disclaims evidence or a claim of edge.
- Repository files were not modified; worktree remained clean.
===CODEX VERDICT END===
