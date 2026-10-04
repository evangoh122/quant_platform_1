# CHECK: residual reversion round 13 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-strategy-residual-reversion-round13.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Build request: .agents/requests/BUILD-strategy-residual-reversion-round13.md (CodeRabbit PR #16 comments). Latest commit "fix(r13): ...".
MiMo says "2/4 new tests FAIL on archived HEAD" — so check each item's test against its own mutation:
1. fetch_data filter uses the SELECTED price column (adj_close on adjusted path). Mutation: filter on raw close again → a test FAILS.
2. _render emits the r10 disclosures (what-changed vs r9, masked-day P&L, understated trial count, no holdout, conclusion) computed from inputs, not
   hard-coded numbers. Mutation: drop one disclosure from _render → a test FAILS. Also: regenerate the report from a synthetic result and compare
   with strategies/results/residual_reversion_r10.md structure.
3. Masked-break test: unmasked control opens a position on the jump day, masked run stays flat. Mutation: ignore the mask → FAILS.
4. Behavioural fetch_data tests (SQL capture, pytest.warns). Mutation: hardcode bronze → FAILS.
No tests deleted/weakened except replaced source-inspection tests. Run python3 -m pytest -q tests/strategies tests/ml.
