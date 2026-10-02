# CHECK-REQUEST (DeepSeek = checker): strategy-residual-reversion

You are the **checker**: read and run, do not modify production code. Branch
`slice/strategy-residual-reversion`, worktree `/home/jianj/code/qp1-strat2`.
Codex's round-1 findings: `.agents/codex/VERDICT-strategy-residual-reversion.md` (item A).
Requests: `BUILD-strategy-residual-reversion-round2.md`, `-round3.md`. Diff: `git diff fe72d1d..HEAD`.

Claude verified LIVE: `gold_tradable_universe` version 2 MERGE deleted 4,077 stale memberships (the
round-1 look-ahead universe); now exactly 300 members on each of 930 days. Results regenerated
after the rebuild: net Sharpe -0.359, OOS net Sharpe -0.514, DSR 0.000; breadth-gated net Sharpe fell
from +0.346 (pre-universe-fix) to +0.007.

Check independently, hardest first:
1. Universe SQL: membership on day t uses only data strictly before t, on a market-calendar grid;
   recency = last 5 market sessions before t. Any remaining way a symbol's own future bars matter?
2. Industry factors: NaN stays NaN; per-date eligible membership; a symbol listed after date d cannot
   change factors/residuals before d. Prove one with a mutated copy under /tmp.
3. ADV cap constrains executed positions, P&L and borrow, not just costs.
4. Walk-forward: parameters chosen on training folds only; purge/embargo; DSR trial count honest.
5. Does `strategies/results/residual_reversion_r2.md` describe exactly what ran? Any claim not backed?

Run `python3 -m pytest tests/strategies -q` from WSL (`wsl -e bash -lc ...`). Verdict APPROVED or
CHANGES_REQUESTED with file:line evidence between `===VERDICT START===` and `===VERDICT END===`;
write it to `.agents/deepseek/VERDICT-strategy-check.md` and commit only that file.
