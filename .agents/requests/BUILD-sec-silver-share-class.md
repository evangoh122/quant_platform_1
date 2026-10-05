# BUILD: SEC silver drops share-class tickers (GOOGL) — fix the universe filter

You are MiMo. Branch `fix/sec-silver-share-class` (worktree qp1-sharecls, off main; stay on it). LF endings, never touch `.agents/dispatch.sh`,
no Databricks. Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-sharecls/.agentlogs/<name>.sh` and run
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-sharecls/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you
change. COMMIT; verdict `.agents/mimo/VERDICT-sec-silver-share-class.md`.
Live facts (Claude): bronze_sec_filings_v2 has 831 GOOGL rows; sec_cik_mapping_log maps both GOOG and GOOGL to CIK 0001652044; gold_tradable_universe
contains GOOG but not GOOGL; silver/05_silver_sec_sections.sql and silver/06_silver_sec_entities.sql keep only `src.ticker IN sec_universe`
(gold_tradable_universe ∪ 16 hardcoded), so GOOGL filings never reach silver and gold_sec_coverage shows GOOG/GOOGL with n_chunks = 0. It is the only one
of 225 bronze tickers dropped.
Fix: in both silver SQL files, extend `sec_universe` with every ticker whose latest mapped CIK (sec_cik_mapping_log, status 'mapped') equals the CIK of a
universe ticker — i.e. include share-class aliases. Do NOT drop the universe filter entirely. Keep the MERGE insert-only semantics.
Tests: the repo's SQL tests (tests/silver/test_silver_sql_semantics.py style — read how they test SQL) asserting the alias join exists and that a GOOGL row
whose CIK matches universe GOOG is selected, while an unrelated non-universe ticker is still excluded. Named mutations: remove the alias union → test
fails; drop the universe filter entirely → test fails. Also check gold/07_gold_sec_coverage.sql still resolves GOOGL → GOOG counts after the fix.
