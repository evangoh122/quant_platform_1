# BUILD-xbrl-B1b round 7 — bug from Claude's LIVE run: the target table is never created

You are MiMo. Branch `feat/xbrl-silver` (stay on it). LF endings, never touch `.agents/dispatch.sh`, no Databricks, no network. Shell rule as before (`.agentlogs/<name>.sh` +
`wsl -d Ubuntu -- bash <path>`; no PowerShell, nothing in C:\temp). Stage only files you change. COMMIT; verdict `.agents/mimo/VERDICT-xbrl-B1b-r7.md`.
Tests may only call production code/SQL; never copy their logic.
Live (Claude, real warehouse): running silver/09_silver_sec_xbrl_facts.sql fails with `[TABLE_OR_VIEW_NOT_FOUND] … silver_sec_xbrl_facts` — the MERGE needs its target, and nothing creates
it (older silver tables were created once by notebooks/archive/00_project_setup.py; a new table has no such step).
1. Add the DDL: `silver/09a_silver_sec_xbrl_facts_ddl.sql` (or a DDL section run first) with `CREATE TABLE IF NOT EXISTS {catalog}.{schema}.silver_sec_xbrl_facts (…)` — every column the
   MERGE INSERT/UPDATE writes, with explicit types matching the MERGE source (and NOT NULL only where the source can never be NULL), USING DELTA. Register it in
   pipelines/run_silver_gold.py so it runs BEFORE the MERGE step (keep other steps unchanged). Same for any table the as-of SQL/view needs.
2. Tests: on an EMPTY DuckDB (no target table) run the production DDL then the production MERGE (twice) — succeeds and is idempotent; the DDL column list equals the MERGE's target
   columns (parse both from the production files). Mutation: remove the DDL step from run_silver_gold.py's step list → a test fails; drop a column from the DDL → a test fails.
