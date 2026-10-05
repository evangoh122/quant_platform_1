# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — xbrl-B1b r5 (saved by Claude)

===VERDICT START===
Reviewer: Codex checker (DeepSeek out of balance)

Status: CHANGES_REQUESTED

Blocking findings:
- `tests/silver/test_sec_xbrl_facts.py:91-116, 925-1000`: mutations survived for `cik`, `taxonomy`, `concept`, `unit`, `period_end`, `fiscal_year`, `fiscal_period`, and `form_type`. These nullable bronze keys are insufficiently tested.
- `silver/09_silver_sec_xbrl_facts.sql:139-150`: eight nullable-key mutations remain undetected and could duplicate rows on rerun.

Checks:
- Focused tests: 32 passed.
- MERGE runs twice: `tests/silver/test_sec_xbrl_facts.py:985-993`.
- Killed: accession_number, period_start, instant, frame.
- Survived: cik, taxonomy, concept, unit, period_end, fiscal_year, fiscal_period, form_type.
- Worktree clean; mutations used only `/tmp` copies.

===VERDICT END===
