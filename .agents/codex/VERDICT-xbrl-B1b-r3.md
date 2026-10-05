# Codex gpt-5.6-sol review round 3 — XBRL B1b (saved by Claude)

===VERDICT START===
Reviewer: Codex sol

Status: APPROVED

Evidence:
- Required checker gate is APPROVED: `.agents/deepseek-fallback/VERDICT-xbrl-B1b-r6.md`.
- Full prescribed suite: 499 passed, 19 skipped.
- Null-safe MERGE equality covers all 12 key columns: `silver/09_silver_sec_xbrl_facts.sql:139-150`.
- All 12 independent `<=>` → `=` mutations were killed in `/tmp`.
- Prior missing-alias regression is fixed: `db/xbrl_queries.py:64-72`; alias mutation was killed.
- Tests capture SQL emitted by `asof_facts()` and execute it through a syntax-only DuckDB translation: `tests/db/test_xbrl_queries.py:169-183`.
- Acceptance-time PIT, restatement ordering, unresolved-accession quarantine, parameter binding, and MERGE idempotency checks pass.
- `git diff --check` passes; worktree remains clean.

===VERDICT END===
