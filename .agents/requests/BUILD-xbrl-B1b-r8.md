# BUILD-xbrl-B1b round 8 — bug from Claude's LIVE run: source rows are not unique per natural key

You are MiMo. Branch `feat/xbrl-silver` (stay on it). LF endings, never touch `.agents/dispatch.sh`, no Databricks, no network. Shell rule as before (`.agentlogs/<name>.sh` +
`wsl -d Ubuntu -- bash <path>`; no PowerShell, nothing in C:\temp). Stage only files you change. COMMIT; verdict `.agents/mimo/VERDICT-xbrl-B1b-r8.md`.
Tests may only call production code/SQL; never copy their logic.
Live (Claude, real Delta): DDL OK; MERGE run 1 inserted 152,703 rows but only 129,822 distinct natural keys (22,881 duplicate groups) — each ticker was ingested exactly ONCE, so the
duplicates come from within a single Company Facts payload (the same fact repeated). MERGE run 2 then failed with
`DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE`.
1. silver/09_silver_sec_xbrl_facts.sql — the MERGE source must have exactly one row per natural key (the 12 ON columns, null-safe): ROW_NUMBER() OVER (PARTITION BY <12 key columns>
   ORDER BY ingested_at DESC, <deterministic tie-break, e.g. value_decimal DESC NULLS LAST, raw_fact_json>) = 1. If rows with the same key disagree on value_decimal, keep the
   chosen row and set a quality flag (e.g. `conflicting_values`) — never silently average or drop. Keep first/last observed timestamps.
2. Tests (production SQL in DuckDB): (a) one bronze run containing two identical facts and two same-key facts with different values → silver has one row per key, the conflict flagged;
   (b) the source SELECT yields unique keys (assert count(*) == count(distinct key) over the production USING select); (c) MERGE twice → no duplicates. Mutation: remove the
   ROW_NUMBER dedupe → (a) and (b) fail.
3. Note in the verdict (no code change): 70,212 of 152,703 facts are `unresolved_accession` (filings older than bronze_sec_filings_v2's 2024-09+ window) — that is by design.
