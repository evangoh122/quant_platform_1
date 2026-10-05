# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — xbrl-B1b r3 (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

- `tests/db/test_xbrl_queries.py:170-186` reconstructs query-building logic instead of calling `asof_facts()`.
- `tests/db/test_xbrl_queries.py:246-307` therefore executes a test-local query; all four DuckDB cases remain green when production `db/xbrl_queries.py` is mutated back to `f.ticker`/`f.concept`.
- `tests/db/test_xbrl_queries.py:309-325` manually constructs the broken query, so it does not prove the production helper mutation fails during execution.

The four silver production mutations pass: `4 passed`; relevant suites: `484 passed, 19 skipped`.
===VERDICT END===
