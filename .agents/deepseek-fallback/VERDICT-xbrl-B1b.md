# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — xbrl-B1b (saved by Claude)

===VERDICT START===
Reviewer: Codex fallback checker

Status: CHANGES_REQUESTED

Blocking findings:
- Required production mutations are not killed. In archived `/tmp` copies, acceptance-time, accession-key, oldest-first, and unresolved-publication mutants all passed 15 tests. Tests use a duplicated transform in `tests/silver/test_sec_xbrl_facts.py:139-300` instead of production SQL.
- `asof_facts` does not match the specified `asof_facts(spark, as_of, …)` helper contract (`db/xbrl_queries.py:24`).

Evidence:
- `pytest -q tests/silver tests/bronze`: 470 passed, 19 skipped.
- Worktree remained clean.
===VERDICT END===
