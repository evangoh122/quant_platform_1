# CHECK: rag-coverage round 9 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-rag-coverage-round9.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Reviewer findings: .agents/reviewer/VERDICT-rag-coverage-r1.md (N1–N5). Build request: BUILD-rag-coverage-round9.md. Commits since the round 9 request.
N1: bronze MERGE uses a unique view per call + process-wide lock around MERGE and its inserted-count read; two concurrent writers → distinct views,
    both batches written, own counts. Mutation: fixed view name / no lock → FAILS. (MiMo mentioned "mock DESCRIBE HISTORY metrics" — confirm the
    inserted count really comes from that MERGE's metrics inside the lock, not from an unlocked history read.)
N2: failed history fetch → ticker recorded failed/partial in sec_ingest_log and the run summary. Test.
N3: global 429/503 cool-down across workers; Retry-After capped (2.3e9 → capped/failure). Tests.
N4: embeddings report the MERGE metric even when 0. Test.
N5: jobs import paths + embeddings environment deps declared; a test enforces it.
No tests deleted/weakened. Run python3 -m pytest tests/rag tests/bronze -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps tests/rag.
