# BUILD-xbrl-B1b round 3 (Codex sol CHANGES_REQUESTED — asof_facts filters reference a missing alias)

You are MiMo. Branch `feat/xbrl-silver` (stay on it). Read `.agents/codex/VERDICT-xbrl-B1b.md`. LF endings, never touch `.agents/dispatch.sh`, no Databricks, no network.
Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`.
No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you change. COMMIT; verdict `.agents/mimo/VERDICT-xbrl-B1b-r3.md`.
db/xbrl_queries.py:64,67 — the optional ticker/concept filters reference alias `f`, which does not exist in the generated query (only `_asof_filtered`), so real
execution fails. Fix the aliasing. The existing fake-Spark tests only inspected the string and encoded the bug — add tests that EXECUTE the generated SQL in DuckDB
(test-only, like tests/silver/test_sec_xbrl_facts.py) for: no filters, ticker filter, concept filter, both; with parameters bound (DuckDB `$name`/`?` equivalent via a
small translation in the test). Mutation: put the `f.` alias back → those tests fail.
