# BUILD-rag-coverage round 12 — IMPLEMENT NOW (Codex sol r4 CHANGES_REQUESTED)

You are MiMo. Fix the P1 in `.agents/codex/VERDICT-rag-coverage-r4.md`. Commit per item, LF endings, do not touch
`.agents/dispatch.sh`, never delete/weaken tests, capture the red phase, mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`.

Unknown ingest metrics still become a job-level zero: `IngestResult.total_rows_appended` starts at int 0
(`pipelines/sec_rag_ingest.py:~1099`); threaded (`~1496`) and serial (`~1516`) aggregation skip None; the summary
(`~1529`) reports 0. Two successful filings whose writer returned None → `rows=0`, which falsely satisfies the idempotency
gate in `docs/SEC_RAG_COVERAGE_RUNBOOK.md:~154`.

Required:
1. `total_rows_appended: Optional[int]`; if ANY successful filing's `rows_appended` is None, the total is None (both modes),
   mirroring the embeddings aggregate. Real zeros stay 0.
2. Summary/log renders unknown explicitly (e.g. `rows=unknown`) — never 0, no TypeError (check every %d / format use and any
   consumer of total_rows_appended, including job outputs/notebook exits/audit rows).
3. Runbook idempotency gate text: state that `unknown` does NOT satisfy the gate (must be proven 0), and what to do.
4. Tests (both threaded and serial): [None, None] → None and rendered "unknown"; [3, None] → None; [0, 0] → 0; [2, 5] → 7.
   Mutation: skip-None aggregation restored → FAILS.
Run: python3 -m pytest tests/rag tests/bronze -q. Verdict: .agents/mimo/VERDICT-rag-coverage-round12.md.
