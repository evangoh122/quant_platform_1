# BUILD-xbrl-B1b — silver XBRL facts + point-in-time as-of view (Plan B slice B1 part b)

You are MiMo. Branch `feat/xbrl-silver` (worktree qp1-xbrl, stacked on feat/xbrl-fundamentals = PR #42; stay on it). LF endings, never touch
`.agents/dispatch.sh`, no Databricks, no network in tests (tests/bronze has a socket guard — add the same autouse guard for your new test dirs).
Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`.
No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you change. COMMIT per item; verdict `.agents/mimo/VERDICT-xbrl-B1b.md`.
Binding spec: docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md §2.3 and §2.5 items 3, 4, 5 (read them fully).
Live inputs (Claude): bronze_sec_xbrl_facts has XOM (2 CIKs), NVDA, AAPL, MSFT, AMD (~130k facts); bronze_sec_filings_v2.accepted_ts holds the SEC
acceptance time per accession.
1. `silver/08_silver_sec_xbrl_facts.sql` (repo SQL style, `{catalog}`/`{schema}` placeholders, MERGE, idempotent): normalise CIK/ticker/concept/unit/dates/
   numerics; `information_available_ts` = bronze_sec_filings_v2.accepted_ts joined on accession_number (NEVER filed_date or ingest time); facts whose
   accession is not found get `quality_status = 'unresolved_accession'` and are kept but excluded from PIT/gold; dedupe repeated ingestions of the same filed
   fact on the natural key in §2.3 (keep latest bronze observation, first/last observed ts); different accessions are different facts (restatements kept).
2. PIT view `silver_sec_xbrl_facts_asof` as a parameterised SQL function or a documented query template + a Python helper `asof_facts(spark, as_of, …)`:
   filter information_available_ts <= as_of, pick latest per cik+taxonomy+concept+unit+period, ordered by information_available_ts DESC, filed_date DESC,
   accession_number DESC. Register both in pipelines/run_silver_gold.py (silver step) without changing other steps.
3. Tests (`tests/silver/test_sec_xbrl_facts.py`; follow tests/silver/test_silver_sql_semantics.py for how SQL is tested): §2.5 items 3, 4, 5 — identical re-ingest
   creates no duplicate; two accessions same period both survive; information_available_ts equals accepted_ts; unresolved accession not published; as-of before
   an amendment returns the original value, after acceptance the amended value. Named mutations: acceptance time → filed_date; drop accession_number from
   the key; sort restatements oldest-first; publish unresolved accessions.
