# CHECK: RAG coverage round 11 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Write .agents/deepseek/VERDICT-rag-coverage-round11.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Request: .agents/requests/BUILD-rag-coverage-round11.md (fixes Codex P1 in .agents/codex/VERDICT-rag-coverage-r3.md).
Commits: 0798921 (red tests), 66a730b, e0ca919. MiMo's self-report is NOT evidence.

Verify:
1. Both writers (`pipelines/sec_rag_ingest.py:~1706-1732`, `pipelines/build_sec_embeddings.py:~284-314`): empty history,
   missing operationMetrics map, missing `numTargetRowsInserted`, and exceptions → None + WARNING; "0" → 0; "7" → 7.
2. Aggregate (`build_sec_embeddings.py:~142-206`): any None batch → total None; [0,0] → 0; no `or 0` coercion anywhere.
3. DOWNSTREAM None-safety (most important): trace every consumer of the now-Optional count — e.g.
   `sec_rag_ingest.py:~1457-1462` `log_entry.rows_appended = inserted`, the ingest audit/log table write (is that column
   nullable in the explicit schema? does createDataFrame accept None?), any sum/`+=`/f-string `:,` formatting, the job summary,
   and the rollout idempotency gate (must treat None as "not proven zero", i.e. NOT pass). Any TypeError on None or any place
   that turns None back into 0 is blocking. Cite each consumer.
4. Tests are behavioural and the red phase is real: in a /tmp copy revert each fix (re-init to 0; restore `or 0`) → named tests FAIL.
Run: python3 -m pytest tests/rag tests/bronze -q.
