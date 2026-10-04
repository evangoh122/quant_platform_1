# CHECK: NL1 round 17 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-nl1-round17.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Your round-16 verdict: .agents/deepseek/VERDICT-nl1-round16.md. Build request: .agents/requests/BUILD-nl1-round17.md. Commit 7275130.
1. No hand-written stand-in view SQL remains in tests (grep tests/analytics_nl for CREATE VIEW / SELECT literals used as views). _ddl_extract helper parses
   docs/NL1_PROPOSED_SERVING_VIEWS.md; the DuckDB shim is minimal and documented.
2. Rerun YOUR round-16 mutations by editing the DOC in a copy — each must FAIL: THEN NULL → THEN -0.99; invalid_return WHEN → WHEN FALSE; remove
   momentum_20d_info_ts from the final GREATEST; add WHERE return_1d IS NOT NULL to with_momentum; remove WHERE rn = 1 from with_splits.
3. CONCERN (Claude): MiMo changed PRODUCTION DDL semantics: "Added COALESCE(return_1d, 0) for NULL handling in cumulative return". A masked/NULL return
   (data-quality break) is then silently treated as 0% inside the cumulative product. Check exactly where it was added and whether it (a) masks the
   invalid_return/NULL propagation built in rounds 14–16, (b) changes semantics for masked breaks vs the documented contract. If it's a semantic change
   to make tests pass, that is a blocking finding — the correct behaviour must be specified (exclude masked days with an explicit coverage flag, or
   NULL the window) and documented.
No tests deleted/weakened except replaced hard-coded SQL copies. Run python3 -m pytest tests/analytics_nl -q; pyspark hidden
PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps; python3 -m analytics_nl.export_schemas --check.
