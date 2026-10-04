# BUILD rag-eval-harness round 10 (builder: MiMo) — small, test-only

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-eval-harness. Descriptive commits.
NEVER delete or weaken existing tests. Checker verdict: .agents/deepseek/VERDICT-rag-eval-harness-round9.md.

1 (blocking). TestProductionWrapperMatchesHarness (tests/rag/test_rag_eval_retrieval.py ~254-277) captures score tuples inside the
   fake reranker, not from `search_sec_filings`' RETURN VALUE. Compare the wrapper's returned results (chunk_id + the score field
   it actually returns — rerank_score if exposed, else similarity; if the wrapper drops rerank_score, expose it in the returned
   dicts so it can be compared) against the harness `hybrid_rerank` output, in order, with approx.
   Mutation proof (in /tmp copy, paste output): perturb ONLY the wrapper's output dicts' score ×1.01 (after reranking, without
   touching shared doc objects) → test FAILS.
2. pytest-timeout: add `pytest-timeout` to the CI install line (.github/workflows/ci.yml ~44) and to requirements (dev/test section
   if one exists, else requirements.txt). Confirm `timeout = 30` is then honoured (no "Unknown config option" warning).
3. conftest.py:88 `socket.setdefaulttimeout(10)` leaks globally. Scope it: set in the guard fixture and restore the previous value
   on teardown (or use a per-socket timeout in the guard tests only). Test: after the guard fixture, `socket.getdefaulttimeout()`
   equals its previous value.
4. TestIsLoopbackValidation tests a LOCAL COPY of `_is_loopback`. Import and test the real function from tests/rag/conftest.py
   (move it to a small importable helper module, e.g. tests/rag/_netguard.py, that conftest imports). Mutation proof: make the
   real function block 127.0.0.2 → a test FAILS.
Acceptance: python -m pytest tests/rag -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) all pass.
.agents/mimo/VERDICT-rag-eval-harness-round10.md with counts + mutation output. Commit everything.
