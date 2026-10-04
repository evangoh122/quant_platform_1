# CHECK: NL1 round 12 (checker: DeepSeek)

Read-only for source. Mutation proofs in /tmp copies (cp -r to /tmp/nl1r12-mut-*). Write .agents/deepseek/VERDICT-nl1-round12.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", numbered findings with file:line, counts,
mutation results. MiMo's self-verdict is not evidence.

Build request: .agents/requests/BUILD-nl1-round12.md (from Codex review .agents/codex/VERDICT-nl1-review.md). Commits: 614c5bf..HEAD.
Verify each of the 5 items and rerun every requested mutation proof yourself:
1. PIT: EVERY proposed view in docs/NL1_PROPOSED_SERVING_VIEWS.md filters input rows by information_available_ts <= :as_of BEFORE any
   window/aggregate (check all views, not just one); output availability = GREATEST over contributing inputs incl. the benchmark.
   Mutation: move the as-of filter after a window → the DDL contract test FAILS.
2. close_price: registry columns checked against the SPECIFIC view's output columns only; the SQL-column checker parses the view SELECT
   list and is non-empty. Mutation: rename a registry column to a non-existent one → FAILS.
3. Coverage: per-metric coverage metadata; status enum incl. INSUFFICIENT_DATA; sample_count/coverage_ratio in responses; aggregate value
   nullable only when INSUFFICIENT_DATA. Tests: IV aggregate 2025 → INSUFFICIENT_DATA; put_call_ratio aggregate 2025 → allowed. Mutation:
   bypass the coverage check → FAILS.
4. Entity min/max counts + allowed entity kinds enforced (one-entity price.compare rejected; sector-level IV trend rejected). Mutation:
   no-op the type check → FAILS.
5. Relative performance: benchmark parameter (SPY/QQQ/RSP) and cumulative return over the window (EXP(SUM(LN(1+r))) − 1 per side); handles
   r <= -1 (LN of non-positive) safely? check.
6. No tests deleted/weakened: git diff 614c5bf..HEAD -- tests. Schemas regenerated (export_schemas --check).
Run: python3 -m pytest tests/analytics_nl -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps; python3 -m analytics_nl.export_schemas --check
(reuse a /tmp venv if needed).
