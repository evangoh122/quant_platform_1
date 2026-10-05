# CHECK: rag-coverage round 8b (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a cp -r of this worktree).
Write .agents/deepseek/VERDICT-rag-coverage-round8b.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Build request: .agents/requests/BUILD-rag-coverage-round8b.md (Codex findings 7–10 of .agents/codex/VERDICT-rag-coverage-review.md). Commits 2100743..HEAD.
ALSO verify Claude's earlier fix commit "test(rag): FakeDataWriter mirrors the accession-keyed MERGE..." (your 8a-2 findings 1–2): 50-chunk new filing →
50 inserted, re-run → 0; history overlap fixture filingFrom ≥ start_date fails on the old `filingFrom < start_date` logic.
For each item 7–10, verify the fix AND that its test fails on the old code:
7. unique temp view per batch + view dropped; MERGEs into one target serialised; inserted count from MERGE metrics; comma ticker list → isin; job env
   declares model deps (resources/jobs.yml).
8. reload_corpus(None) no longer triggers a full collect (spy); NULL/unparseable accepted_ts chunks never returned for any as_of.
9. gold/07 uses catalog/schema placeholders the runner substitutes; rows restricted to the universe (out-of-universe counted/logged); CIK from latest
   mapped sec_cik_mapping_log entry. DuckDB test runs the SQL extracted from the file with exact rows.
10. table errors → retrieval_unavailable, substring path not called. Bronze MERGE uses explicit columns.
No tests deleted/weakened. Run python3 -m pytest tests/rag tests/bronze -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps tests/rag.
