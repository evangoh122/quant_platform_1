# CHECK: RAG coverage rounds 18–18c (checker: DeepSeek) — CodeRabbit PR #28 findings

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`. Write .agents/deepseek/VERDICT-rag-coverage-round18.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line evidence.
Findings: .agents/claude/coderabbit-pr28.md. Requests: BUILD-rag-coverage-round18-coderabbit.md, -round18b.md, -round18c.md.
Commits 8e48d53..081b017 (+ Claude tiny fix af75e69). Claude (WSL): `pytest tests/rag tests/bronze --timeout 30` → 1144 passed in 32 s.
Verify all 8 CodeRabbit items with a test that fails on the old code (run the mutation): (1) SEC overflow history files parsed (top-level arrays);
(2) share-class aliases (GOOG/GOOGL, FOX/FOXA, NWS/NWSA): one stored copy, every alias resolves via the CACHED alias map (no per-query Spark);
(3) gold coverage includes silver's hardcoded tickers; (4) offline evals Spark-free; (5) runbook repeats catalog/schema/secret args after `--`;
(6) bounded accepted_before_filing check; (7) XBRL client uses the pipeline User-Agent resolver, never logs it; (8) placeholder-email check.
Also: tests never touch the network (socket/DNS guard), and the alias map cache is invalidated sensibly (TTL or per process) — no stale
alias after a coverage refresh lasting forever. Run: python3 -m pytest tests/rag tests/bronze -q --timeout 30.
