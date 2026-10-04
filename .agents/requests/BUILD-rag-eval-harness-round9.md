# BUILD rag-eval-harness round 9 (builder: MiMo) — small, test-only round

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-eval-harness. Commit with descriptive messages.
NEVER delete or weaken existing tests. Checker verdict: .agents/deepseek/VERDICT-rag-eval-harness-round8.md.

1 (blocking). `TestProductionWrapperMatchesHarness` (tests/rag/test_rag_eval_retrieval.py ~189-262, assertion ~254) compares
   chunk ids only. Compare `(chunk_id, score)` tuples in order (production `search_sec_filings` result vs harness), using
   pytest.approx(rel=1e-9) for scores. Mutation proof in /tmp copy: perturb the score in one path (e.g. multiply by 1.01 in
   the production wrapper only) → this test FAILS. Paste the output.
2. Restore the exact-string assertion in tests/rag/test_rag_eval_report.py ~221 (`"relative/corpus.jsonl"`), keep the Path check too.
3. Test dict-KEY redaction in evals/rag_eval/report.py: `{Path("/home/x/k.jsonl"): 1, "/tmp/a/b": 2}` → keys become basenames.
4. `_is_loopback` in tests/rag/conftest.py: use `ipaddress.ip_address(host).is_loopback` (with ValueError → only the literal
   "localhost" is loopback). Test: "127.1.evil.com" is BLOCKED; "127.0.0.2" and "::1" allowed.
5. Add `--timeout` safety (pytest-timeout if available, else a socket default timeout in the guard tests) so a broken guard
   fails fast instead of hanging.

Acceptance: python -m pytest tests/rag -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) all pass.
.agents/mimo/VERDICT-rag-eval-harness-round9.md with counts + mutation output. Commit everything.
