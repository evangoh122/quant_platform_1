# CHECK: XBRL B1a round 10 (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r9 verdict: .agents/deepseek-fallback/VERDICT-xbrl-B1a-r9.md. Fix ad1d2cd (spec .agents/requests/BUILD-xbrl-B1a-r10.md). Claude: tests/bronze +
tests/rag/test_sec_rag_ingest.py → 556 passed; no BRONZE_FACT_COLUMNS / MANIFEST_COLUMNS / "http_status INT" left in the pipeline.
1. ALTER derives missing columns and types from the StructType (fake table missing two fields → one ALTER with both). Mutation: hard-code a column → fails.
2. No hand-written column list anywhere for these tables.
3. Socket guard: any test in tests/bronze that opens a socket fails; `test_fallback_when_volumes_not_writable` is hermetic. Mutation: let it fetch for real
   → the guard fails the test.
4. Re-run every earlier B1a mutation; run the offline suite.
