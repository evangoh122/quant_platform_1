# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — xbrl-B1b r4 (saved by Claude)

===VERDICT START===
Status: APPROVED

- `tests/db/test_xbrl_queries.py:243-299` calls `asof_facts()` and executes captured production SQL; no query reconstruction.
- `tests/silver/test_sec_xbrl_facts.py:177-204` reads production SQL directly.
- DB/silver suites: 131 passed, 2 skipped.
- `f.ticker` and `f.concept` mutations each caused 4 failures.
- Four silver mutations: 4 passed.
===VERDICT END===
