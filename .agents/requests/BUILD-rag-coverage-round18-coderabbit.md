# BUILD-rag-coverage round 18 — IMPLEMENT NOW (CodeRabbit findings on PR #28)

You are MiMo. Stay on branch `slice/rag-coverage` (do not create/switch branches). Commit per item, LF endings, do not touch
`.agents/dispatch.sh`, never weaken tests, capture the red phase, paste each mutation's FAILED output into your verdict.
Full CodeRabbit text: `.agents/claude/coderabbit-pr28.md` + PR #28 inline comments. Fix all 8:
1. MAJOR pipelines/sec_rag_ingest.py:~867-878 — SEC overflow history files (`CIK##########-submissions-001.json`, listed in `filings.files`) hold
   accessionNumber/filingDate/form/primaryDocument/acceptanceDateTime as TOP-LEVEL arrays; only the main file nests them under `filings.recent`.
   Parse both shapes; fix the fixture `tests/rag/fixtures/sec/submissions_history.json` to the real top-level shape. Test: a 10-K only present in
   a history file is discovered. Mutation: read only `filings.recent` → FAIL.
2. MAJOR :~1396 share classes on one CIK (GOOG/GOOGL, FOX/FOXA, NWS/NWSA): keep ONE stored copy of each filing (no duplicate chunks/embeddings);
   model share classes as aliases — a canonical ticker per CIK for storage, and gold_sec_coverage + retrieval resolve every alias ticker to the
   canonical one (coverage rows for all aliases; `check_ticker_coverage("GOOGL")` succeeds and returns GOOG-stored chunks labelled with the
   requested ticker). Log/audit records the alias. Tests for both directions. Mutation: drop alias resolution → FAIL.
3. MAJOR gold/07_gold_sec_coverage.sql:~16 — include silver's hardcoded ticker set in the coverage universe (a ticker with silver chunks but absent
   from gold_tradable_universe must still get a coverage row). Test via the SQL/text contract or a DuckDB/Spark-free rendering test.
4. MAJOR evals/rag_eval/corpus.py:~462 — offline hybrid evaluations must not need Spark: answer coverage from the offline ticker groups, bypass the
   LRU size limit when installing them, and restore the original checker + cache on exit. Test with Spark absent.
5. docs/SEC_RAG_COVERAGE_RUNBOOK.md:~53 — `databricks bundle run <job> -- <args>` REPLACES task parameters: every command must repeat
   --catalog/--schema/--user-agent-secret-scope/--user-agent-secret-key (or move them to job-level parameters in resources/jobs.yml and document).
6. Runbook :~115 — `accepted_before_filing` check: bound with a tolerance (e.g. accepted_ts < filing_date − 4 days) or document that after-hours
   filings make non-zero counts expected; prefer the bounded check.
7. api/services/xbrl_client.py:~30 — the API XBRL client needs a User-Agent in the app: reuse the pipeline resolver (env SEC_EDGAR_USER_AGENT or
   the Databricks secret) instead of an unset EDGAR_USER_AGENT; never log the value. Test.
8. notebooks/refresh_bronze_cot.py:~75 — reject placeholder addresses (example.com/.org/.net domains, `your-email@`, etc.) without rejecting valid
   addresses that merely contain "example" (e.g. analyst@myexample.org). Same fix for the SEC user-agent validator if it uses a bare substring.
Run: python3 -m pytest tests/rag tests/bronze -q (WSL has pyspark; also make sure the no-pyspark path still works — CI has no pyspark).
Verdict: .agents/mimo/VERDICT-rag-coverage-round18.md.
