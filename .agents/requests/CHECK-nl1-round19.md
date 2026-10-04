# CHECK: NL1 round 19 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-nl1-round19.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Codex review being fixed: .agents/codex/VERDICT-nl1-review4.md. Request: BUILD-nl1-round19.md. Commits since the round 19 request.
Rerun Codex's probes/mutations — each must now FAIL/behave:
1. (0,0) and invalid stats (sample > total, negatives) → INSUFFICIENT_DATA / reject for IV trend/compare/rank/aggregate. Mutation: restore `if total_count > 0`.
2. Bronze fallback views: output availability = GREATEST(derived_ts, ingest_ts); DuckDB test on the EXTRACTED doc views (Jan 2 row ingested Jan 5 →
   Jan 5). Mutation: drop ingest_ts from the GREATEST in the DOC → FAILS.
3. Registry fail-closed (unsupported keys, unknown tokens/slots, open scalar types, extra pairs, unused views, unknown param types, out-of-bounds
   defaults) — each malformed variant raises.
4. Policy bounds loading raises PolicyValidationError on missing/malformed limits (types, positivity, ordering, version, exact keys) — no .get defaults.
5. Drop `adj.information_available_ts` from the GREATEST at docs ~172 → FAILS.
Also confirm no production view semantics were changed beyond item 2, and the round 16–18 doc mutations are still killed.
Run python3 -m pytest tests/analytics_nl -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps;
python3 -m analytics_nl.export_schemas --check.
