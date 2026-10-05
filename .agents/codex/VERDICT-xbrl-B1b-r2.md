# Codex gpt-5.6-sol review round 2 — XBRL B1b (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

- `silver/09_silver_sec_xbrl_facts.sql:139-149`: the MERGE is not idempotent for quarantined facts with a null `accession_number`; `tgt.accession_number = src.accession_number` never matches nulls, so every rerun inserts another copy. The same issue affects nullable `cik`, `taxonomy`, and `concept`, despite the stated null-safe composite-key contract. The semantic tests do not catch this because `tests/silver/test_sec_xbrl_facts.py:190-191` deletes the target and executes only the extracted INSERT source rather than the production MERGE.

Validation:
- Required suite: 484 passed, 19 skipped.
- Prior alias finding is fixed.
- Independent `/tmp` mutations killed both alias regressions and all four required silver semantic regressions.
- Worktree remained unchanged.
===VERDICT END===
