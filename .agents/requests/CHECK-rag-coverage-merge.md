# CHECK: RAG coverage — merge of origin/main + post-merge fixes (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Write .agents/deepseek/VERDICT-rag-coverage-merge.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
The branch was fully approved (DeepSeek r15, Codex r6, Claude final + live AAPL ingest). Since then: merge 5ba57e4 (origin/main incl. #16, #26, #27),
8b792dc (r16c tests), 787e725 (fixture sys.modules restore + isolation guards). Requests: BUILD-rag-coverage-round16-merge.md, -16b, -16c, -16d.
Claude (WSL): `pytest tests/rag tests/bronze` → 1128 passed, 0 failed; origin/main alone → 892 passed.
Verify: (1) per conflicted file (agent/tools_retrieval.py, docs/DATA_SCHEMAS.md, pipelines/run_silver_gold.py, resources/jobs.yml,
tests/rag/conftest.py, tests/rag/test_hybrid_retriever.py) nothing from EITHER side was dropped — diff against both parents
(`git show 5ba57e4^1:<f>`, `git show 5ba57e4^2:<f>`); search_sec_filings keeps no_coverage/ticker_required AND main's retrieve_and_rerank AND
main's PIT substring fallback, and NoCoverage never reaches the fallback; jobs.yml keeps every job from both sides incl. the user-agent secret
params. (2) No test was deleted or weakened in the merge or after (count test defs vs both parents). (3) The fixture fix truly restores sys.modules
(mutation: revert it → the bronze test fails again when run after test_sec_rag_ingest.py). (4) Branch-specific invariants still hold
(rows=unknown semantics, secret resolution, value-leak tests, coverage gating).
Run: python3 -m pytest tests/rag tests/bronze -q; python3 -m pytest -q -m "not spark and not lakebase and not databricks" (report counts).
