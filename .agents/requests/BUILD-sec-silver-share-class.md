# BUILD: share-class tickers (GOOGL) show no SEC coverage — fix the canonical-ticker rule

You are MiMo. Branch `fix/sec-silver-share-class` (worktree qp1-sharecls, off main; stay on it). LF endings, never touch `.agents/dispatch.sh`,
no Databricks, no network. Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-sharecls/.agentlogs/<name>.sh` and run
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-sharecls/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you
change. COMMIT per item; verdict `.agents/mimo/VERDICT-sec-silver-share-class.md`.
(An earlier attempt on this branch changed the silver universe filter; it was a wrong diagnosis and has been reset — do not redo it.)
Live facts (Claude): silver_sec_sections HAS 831 GOOGL chunks (CIK 0001652044); gold_tradable_universe has both GOOG and GOOGL; sec_cik_mapping_log maps
both to 0001652044. But gold_sec_coverage shows GOOG and GOOGL with n_chunks = 0 and the agent returns no_coverage for GOOGL, because:
- gold/07_gold_sec_coverage.sql:42-58 picks the canonical ticker per CIK as `min(ticker)` (alphabetically first → GOOG), then counts the canonical's chunks
  — GOOG has none, the data is stored under GOOGL.
- api/services/hybrid_retriever.py `_load_alias_map` (~"Group tickers by CIK → pick canonical (alphabetically first)") maps GOOGL → GOOG, so retrieval
  loads GOOG's (empty) corpus.
Fix: the canonical ticker for a CIK group is the ticker that actually holds the silver chunks (most chunks; tie → alphabetical), in BOTH places, so
they agree. In 07, compute per-ticker chunk counts from silver_sec_sections and choose the canonical by max(n_chunks) then ticker. In _load_alias_map,
read n_chunks from gold_sec_coverage (already selected there? add it to the query; parameter-free constant SQL) and choose likewise; keep alias resolution
for tickers with zero chunks pointing at the canonical with data.
Tests: SQL semantics test for 07 (repo style: tests/silver/test_silver_sql_semantics.py or tests/gold) — a CIK with GOOG (0 chunks) and GOOGL (831) →
canonical GOOGL and both rows report 831; a normal single-ticker CIK unchanged. hybrid_retriever: alias map built from fake coverage rows maps GOOG → GOOGL
and GOOGL → GOOGL; check_ticker_coverage('GOOG') and ('GOOGL') both succeed with the fake. Named mutations: revert to min(ticker) in 07 → fails; revert
to sorted()[0] in _load_alias_map → fails.
