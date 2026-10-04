# CHECK: rag-coverage round 7 (checker: DeepSeek)

Read-only for source. Mutation proofs in /tmp copies. Write .agents/deepseek/VERDICT-rag-coverage-round7.md between ===VERDICT START=== /
===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line, counts, mutation results.
Build request: .agents/requests/BUILD-rag-coverage-round7.md. Your round-6 verdict: .agents/deepseek/VERDICT-rag-coverage-round6.md.
Commit: the latest "fix(tests): scope pyspark/databricks fakes..." (MiMo timed out before writing its verdict; Claude committed its work).

Claude's observation (verify): `python3 -m pytest tests/rag tests/bronze -q` → 583 passed, 36 skipped, 0 failed; the 7 COT spark tests now
SKIP ("No local PySpark session available") both combined AND alone. Before, they "passed alone" only because system python's
databricks-connect silently created a LIVE Databricks serverless session (network in unit tests). CI has no pyspark, so they skip in CI too.
Decide whether that is acceptable (consistent, no network) or a weakening, and say why.
Verify:
1. The module-scoped fixture in tests/rag/test_sec_rag_ingest.py restores sys.modules exactly (incl. names absent before); no other
   module-level sys.modules mutation remains under tests/rag (grep); the setdefault loop near :971-980 — does it leak?
2. tests/rag/test_zz_isolation.py really detects a leak: mutation in /tmp copy — re-add the module-level
   `sys.modules.setdefault("databricks.connect", MagicMock())` → the isolation test FAILS when run after test_sec_rag_ingest.py.
3. The COT spark fixture guard: what exactly does it check? Does it still allow a real LOCAL pyspark SparkSession (so the tests run where
   pyspark is installed)?
4. Comment at pipelines/sec_rag_ingest.py ~385 no longer mentions `ambiguous`.
5. No tests deleted/weakened: git diff 0f4cb1c..HEAD -- tests.
Run: python3 -m pytest tests/rag tests/bronze -q -rs; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q.
