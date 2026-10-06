# BUILD: share-class fix round 2 (Codex CHANGES_REQUESTED — SQL and API still disagree)

You are MiMo. Branch `fix/sec-silver-share-class` (stay on it). Read `.agents/codex/VERDICT-sec-share-class.md`. LF endings, never touch `.agents/dispatch.sh`,
no Databricks, no network. Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-sharecls/.agentlogs/<name>.sh` and run
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-sharecls/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you change.
COMMIT; verdict `.agents/mimo/VERDICT-sec-share-class-r2.md`.
gold_sec_coverage reports the canonical's n_chunks on every alias row (GOOG=831, GOOGL=831), so `_load_alias_map` sees a tie and picks GOOG again.
1. gold/07_gold_sec_coverage.sql: add a `canonical_ticker` column (the ticker chosen by max(raw n_chunks) then alphabetical) to every row.
2. api/services/hybrid_retriever.py `_load_alias_map`: read `ticker, canonical_ticker` from gold_sec_coverage (Spark and warehouse paths; constant SQL) and use
   canonical_ticker directly — no re-derivation. If the column is missing (old table), fall back to identity mapping with a WARNING (never guess
   alphabetically).
3. Tests: integration-shaped fake gold rows exactly as 07 emits them (GOOG: n_chunks 831, canonical GOOGL; GOOGL: 831, canonical GOOGL) → both resolve to
   GOOGL; 07 SQL test asserts canonical_ticker = GOOGL for both rows. Mutation: re-derive canonical in Python from n_chunks → the new test fails; alphabetical
   fallback when the column is missing → test fails.
