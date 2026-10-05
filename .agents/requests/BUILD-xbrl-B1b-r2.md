# BUILD-xbrl-B1b round 2 (checker CHANGES_REQUESTED — tests exercise a copy, not production SQL)

You are MiMo. Branch `feat/xbrl-silver` (stay on it). Read `.agents/deepseek-fallback/VERDICT-xbrl-B1b.md`. LF endings, never touch `.agents/dispatch.sh`,
no Databricks, no network. Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you change.
COMMIT; verdict `.agents/mimo/VERDICT-xbrl-B1b-r2.md` with each mutation's FAILED output (mutate the production SQL/helper in a /tmp `git archive` copy).
1. tests/silver/test_sec_xbrl_facts.py:139-300 duplicates the transform. Delete the duplicate and test the PRODUCTION SQL the same way
   tests/silver/test_silver_sql_semantics.py does (read silver/09_*.sql, extract the source SELECT/CTEs, substitute `{catalog}.{schema}` tables with DuckDB test
   tables, execute in DuckDB — DuckDB is a test-only tool here, already used by that file). Where Spark-only syntax blocks DuckDB, keep the logic in a CTE that
   DuckDB can run, or add a minimal documented translation step — but the assertions must run against the production text.
2. The four named mutations must each fail: information_available_ts from filed_date instead of accepted_ts; accession_number dropped from the natural key;
   restatements ordered oldest-first in the as-of selection; unresolved accessions published.
3. db/xbrl_queries.py: implement the specified contract `asof_facts(spark, as_of, …)` (spark session, as_of datetime, optional ticker/concept filters) returning a
   DataFrame from the production as-of SQL with `as_of` bound as a parameter (`spark.sql(query, args={...})`); unit test with a fake spark that records the SQL and
   args (no f-string values).
