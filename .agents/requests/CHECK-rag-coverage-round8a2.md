# CHECK: rag-coverage round 8a-2 (checker: DeepSeek)

Read-only. For mutation proofs build copies with `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a cp -r of this worktree).
Write .agents/deepseek/VERDICT-rag-coverage-round8a2.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Your round-8a verdict: .agents/deepseek/VERDICT-rag-coverage-round8a.md. Build request: .agents/requests/BUILD-rag-coverage-round8a2.md. Commit 32548c1.
1. Inserted count = actual inserted ROWS from the Delta MERGE (target-table operationMetrics or MERGE result), dead temp-view DESCRIBE HISTORY removed;
   FakeDataWriter mirrors MERGE (re-run → 0). 50-chunk filing → 50; re-run → 0.
2. Concrete SparkIngestLogReader with pushed-down predicates, constructed in main() (wiring test); resume skips succeeded; attempt = max + 1.
3. Rerun YOUR three surviving mutations from 8a — each test must now FAIL on the old code: history overlap (filingFrom ≥ start_date), acceptance array
   shorter than forms, stale cache with an old .meta sidecar.
No tests deleted/weakened. Run python3 -m pytest tests/rag tests/bronze -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps tests/rag.
