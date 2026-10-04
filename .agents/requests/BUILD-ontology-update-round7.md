# BUILD ontology round 7 (author: Codex gpt-5.6-sol) — small fixes from checker check6

Edit files only (you cannot commit or write .agents/). Print a report between ===REPORT START=== and ===REPORT END===.
Checker verdict: .agents/deepseek/VERDICT-ontology-update-check6.md (CHANGES_REQUESTED, one blocker).

1 (blocker). ontology/table_semantics.yaml:65 lists `missing_cik` as a sec_ingest_log status. The code
   (slice/rag-coverage:pipelines/sec_rag_ingest.py) emits only planned, in_progress, succeeded, failed, skipped_existing.
   Remove it; note that unmapped tickers are recorded in sec_cik_mapping_log (missing/ambiguous). Add a test asserting the
   ontology's sec_ingest_log statuses equal the set emitted by the code (read the branch file via `git show` in the test
   only if the repo already does that pattern; otherwise a snapshot fixture with a comment citing branch:path:line).
2. gold_sec_coverage: say rows are NOT limited to the universe (FULL OUTER JOIN in
   slice/rag-coverage:gold/07_gold_sec_coverage.sql) — tickers with filings/chunks outside the universe also appear;
   consumers filter by universe membership.
3. Adjusted-path realized_volatility / drawdown / momentum: state that the proposed DDL drops null-return rows before
   computing; and that the semantic registry currently defaults to the unadjusted fallback
   (`adjusted_source_available: false`) until silver_ohlcv_day_adjusted is live.
4. Do NOT change the corporate-actions section yet (that lane is mid-round; it'll be refreshed after merge).
Run python3 -m pytest tests/test_ontology.py -q and report counts.
