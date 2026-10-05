# BUILD-xbrl-B1b round 5 (Codex sol CHANGES_REQUESTED — MERGE not idempotent for null keys)

You are MiMo. Branch `feat/xbrl-silver` (stay on it). Read `.agents/codex/VERDICT-xbrl-B1b-r2.md`. LF endings, never touch `.agents/dispatch.sh`, no Databricks, no network.
Shell rule as before (`.agentlogs/<name>.sh` + `wsl -d Ubuntu -- bash <path>`; no PowerShell, nothing in C:\temp). Stage only files you change. COMMIT; verdict
`.agents/mimo/VERDICT-xbrl-B1b-r5.md` with FAILED output for the mutation (mutate in a /tmp `git archive` copy).
Tests may only call production code/SQL; never copy their logic.
1. silver/09_silver_sec_xbrl_facts.sql:139-149 — make every key comparison in the MERGE ON clause null-safe (`<=>`, Spark's null-safe equality) for all nullable natural-key
   columns (accession_number, cik, taxonomy, concept, unit, period fields, frame …) so a rerun never inserts a duplicate quarantined fact.
2. Test the PRODUCTION MERGE, not just its INSERT source: tests/silver/test_sec_xbrl_facts.py:190-191 currently deletes the target and runs only the source SELECT. Execute the
   real MERGE statement twice against the same fixture (DuckDB supports MERGE in recent versions — check `duckdb.__version__`; if unsupported, translate ONLY `<=>` to
   `IS NOT DISTINCT FROM` and the table names, nothing else) and assert the row count is unchanged after the second run, including rows with null accession_number/cik.
   Mutation: replace `<=>` with `=` for accession_number → the rerun test fails.
