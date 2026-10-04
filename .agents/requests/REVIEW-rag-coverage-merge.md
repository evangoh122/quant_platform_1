# REVIEW: RAG coverage — merge of origin/main + post-merge fixes (reviewer: Codex gpt-5.6-sol)

You APPROVED the branch at r6 (.agents/codex/VERDICT-rag-coverage-r6.md). Since then: merge 5ba57e4 (origin/main incl. #16, #26, #27),
8b792dc (post-merge tests), 787e725 (fixture sys.modules snapshot restore + isolation guards; Claude tiny fix). DeepSeek APPROVED the merge:
.agents/deepseek/VERDICT-rag-coverage-merge.md. Claude (WSL): `pytest tests/rag tests/bronze` → 1128 passed.
Do NOT edit repo files; mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Focus ONLY on what changed since your r6 approval: per conflicted file, nothing dropped from either parent (agent/tools_retrieval.py —
no_coverage/ticker_required + retrieve_and_rerank + main's PIT substring fallback, NoCoverage never falls through; resources/jobs.yml — every job
from both sides incl. user-agent secret params; pipelines/run_silver_gold.py; docs/DATA_SCHEMAS.md; tests/rag/conftest.py;
tests/rag/test_hybrid_retriever.py), no weakened tests, and the fixture restore is correct. Your r3–r6 invariants must still hold.
Print verdict between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line.
Run: python3 -m pytest tests/rag tests/bronze -q
