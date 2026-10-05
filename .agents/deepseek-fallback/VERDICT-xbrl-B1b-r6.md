# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — xbrl-B1b r6 (saved by Claude)

===VERDICT START===
Reviewer: Codex checker (DeepSeek out of balance)

Status: APPROVED

Evidence:
- Production `MERGE ON` uses null-safe `<=>` for all 12 columns: `silver/09_silver_sec_xbrl_facts.sql:139-150`.
- Parametrized coverage tests all 12 nullable columns: `tests/silver/test_sec_xbrl_facts.py:1162-1198`.
- Production `MERGE` runs twice: `tests/silver/test_sec_xbrl_facts.py:1216-1222`.
- Baseline: 30 passed.
- All 12 individual `<=>` → `=` mutations failed as expected.
- Worktree clean; mutations were performed only in `/tmp` git-archive copies.

===VERDICT END===
