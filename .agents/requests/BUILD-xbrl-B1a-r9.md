# BUILD-xbrl-B1a round 9 (DeepSeek CHANGES_REQUESTED on r7+r8 — DDL and StructType can drift)

You are MiMo. Branch `feat/xbrl-fundamentals` (stay on it). Read `.agents/deepseek/VERDICT-xbrl-B1a-r7r8.md`. LF endings, never touch
`.agents/dispatch.sh`, no Databricks. Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you
change. COMMIT; verdict `.agents/mimo/VERDICT-xbrl-B1a-r9.md`.
Make the StructType the single source of truth for BOTH tables: generate the `CREATE TABLE IF NOT EXISTS … (…)` column list from the bronze and
manifest StructTypes (name + Spark SQL type via `field.dataType.simpleString()`, NOT NULL where nullable=False) instead of a hand-written DDL string.
Test: parse the generated DDL's column list and assert it equals the StructType (names, order, types) for both tables; and the ALTER-missing-columns
logic is driven by the same StructType. Paste FAILED output: drop a field from the StructType → contract test fails (the DDL can no longer drift
separately; say so in the verdict). Keep the live behaviour identical (existing tables already have these columns).
