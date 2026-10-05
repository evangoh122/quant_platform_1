# REVIEW round 2: XBRL B1b — silver facts + point-in-time as-of view (reviewer: Codex sol)

Branch feat/xbrl-silver (stacked on PR #42). Plan B §2.3, §2.5 items 3–5 (your plan). Commits c69f5af (build) and the round-2 commit (tests execute the PRODUCTION
silver/09_*.sql in DuckDB as tests/silver/test_silver_sql_semantics.py does; db/xbrl_queries.asof_facts(spark, as_of, …) binds as_of). Checker (Codex luna, DeepSeek
out of balance): r1 CHANGES_REQUESTED (tests used a duplicated transform) → r2 APPROVED (.agents/deepseek-fallback/VERDICT-xbrl-B1b-r2.md; the four production
mutations killed). Claude: tests/silver + tests/bronze 470 passed.
Run `python3 -m pytest tests/silver tests/bronze tests/db -q`. Mutation proofs only in /tmp via `git archive HEAD`. Judge: PIT correctness (acceptance time, never
filed_date/ingest time), restatements kept per accession, as-of selection order, unresolved accessions quarantined, MERGE idempotency, SQL safety, the Spark SQL vs
DuckDB translation (does the test still exercise what Spark runs?). Print the verdict between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or
"Status: CHANGES_REQUESTED" and file:line. Do not edit files.

## Round 2 delta
Your r1 verdict: .agents/codex/VERDICT-xbrl-B1b.md (asof_facts filters referenced alias `f`). Fixes 6dcea02 (alias) and de9d04f (tests capture the SQL asof_facts()
emits and execute it in DuckDB). Checker luna: r3 CHANGES_REQUESTED (tests reconstructed the query) → r4 APPROVED (.agents/deepseek-fallback/VERDICT-xbrl-B1b-r4.md).
Claude: tests/db 14 passed; production `f.ticker` mutation → 4 failed. Confirm your finding is fixed.
