# CHECK: bronze-refresh CodeRabbit round (DeepSeek, independent checker)

Branch `slice/bronze-refresh`, commit 206bc5a (MiMo, fixing PR #17 CodeRabbit findings).
The request is `.agents/requests/BUILD-bronze-coderabbit.md`; MiMo's verdict is
`.agents/mimo/VERDICT-bronze-coderabbit.md`. Read-only: do scratch work under /tmp.
Write `.agents/deepseek/VERDICT-bronze-coderabbit-check.md` between
===VERDICT START===/===VERDICT END===, with Status APPROVED or CHANGES_REQUESTED.

Check, hardest first:
1. **Fed dedup** (`select_new_rows`, `_get_existing_keys`).
   - Same value on a later day → 0 new. Changed value → new vintage.
   - A→B→A → the revert is new.
   - Still append-only.
   - Ties within the same vintage_date: is "latest" deterministic?
   - Float equality: could an unchanged value re-parse unequal?
   - Claude's live dry-run on a new day: 5 new, ~221 overlap, 0 dups.
2. Every item 1-9 in the request: fixed, or justified not-applicable? Check the evidence.
3. Did the fixes break the H.15 availability calendar or point-in-time rules?
   Run the fed tests.
4. Exit codes: does options/fed `main` return nonzero on partial failure, and does the
   notebook entrypoint propagate it?
5. Would the new tests catch a regression to a vintage-dependent key? Prove it with a /tmp mutation.

Run `python3 -m pytest tests/bronze -q`.
