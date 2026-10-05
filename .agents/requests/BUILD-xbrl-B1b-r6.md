# BUILD-xbrl-B1b round 6 (checker CHANGES_REQUESTED — eight nullable-key mutations survive)

You are MiMo. Branch `feat/xbrl-silver` (stay on it). Read `.agents/deepseek-fallback/VERDICT-xbrl-B1b-r5.md`. LF endings, never touch `.agents/dispatch.sh`, no Databricks,
no network. Shell rule as before (`.agentlogs/<name>.sh` + `wsl -d Ubuntu -- bash <path>`; no PowerShell, nothing in C:\temp). Stage only files you change. COMMIT; verdict
`.agents/mimo/VERDICT-xbrl-B1b-r6.md`. Tests may only call production SQL; never copy its logic.
Add ONE parametrized test over every nullable natural-key column of the MERGE ON clause (cik, taxonomy, concept, unit, period_start, period_end, instant, fiscal_year,
fiscal_period, form_type, accession_number, frame): insert a bronze fact with THAT column NULL (all others set), run the production MERGE twice, assert the row count is
unchanged and the fact appears exactly once. If the production source SELECT filters out NULLs for a column before the MERGE (so a `=` mutation is harmless), the parametrized case
must instead assert the fact is excluded/quarantined by that filter — and say so per column in the verdict. Paste FAILED output for `<=>`→`=` on cik, concept, fiscal_year and
form_type (mutate in a /tmp `git archive` copy).
