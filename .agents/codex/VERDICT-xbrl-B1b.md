# Codex gpt-5.6-sol review — XBRL B1b (saved by Claude)

===VERDICT START===
Reviewer: Codex

Status: CHANGES_REQUESTED

Finding:
- `db/xbrl_queries.py:64` and `db/xbrl_queries.py:67`: optional filters reference alias `f`, but the enclosing query exposes only `_asof_filtered` at line 72. Real SQL execution fails with `Referenced table "f" not found`, so `asof_facts(..., ticker=...)` and `asof_facts(..., concept=...)` are unusable. Existing fake-Spark tests merely inspect the generated string and encode the invalid alias.

Validation:
- Required suite: 479 passed, 19 skipped.
- Independent `/tmp` archive mutations: all four were killed—acceptance time, accession key, restatement ordering, and unresolved-accession quarantine.
- Worktree remained clean.

===VERDICT END===
