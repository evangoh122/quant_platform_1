# CHECK: rag-eval-harness round 11 (checker: DeepSeek)

Read-only for source. Mutation proofs in /tmp copies (cp -r to /tmp/h11-mut-*). Write .agents/deepseek/VERDICT-rag-eval-harness-round11.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line, counts, mutation results.
Build request: .agents/requests/BUILD-rag-eval-harness-round11.md (from Codex review .agents/codex/VERDICT-rag-eval-harness-review2.md).
Commits: since the "harness round 11 request" commit.
Verify, rerunning Codex's probes:
1. Metrics: dedupe before top-k for recall/MRR/nDCG; nDCG in [0,1]; ["g","g"] vs ["g"] → 1.0; zero-gold answerable rows excluded and counted.
   The randomized reference in the TEST must be independent of production (not imported) and run ≥ 500 seeded cases incl. duplicates,
   empty rankings, k > len. Mutation: remove the dedupe → the property test FAILS.
2. Ticker-filter-off: query "NVIDIA revenue", ticker filter off → bm25, dense, hybrid_rrf, hybrid_rerank all run with NO ticker filter
   (assert the filter actually applied); production default unchanged (ticker still derived when not disabled). Mutation → FAILS.
3. Offline: `_FakeEmbeddingProvider` is autouse in tests/rag/conftest.py. Check it doesn't make OTHER retrieval tests vacuous — do tests that
   assert semantic ranking (dense similarity order) still verify something meaningful with hash-seeded vectors, or did any assertion get
   relaxed? Confirm no HF download/model load: run with HF_HUB_OFFLINE=1 and the network guard; report runtime.
4. Substring fallback results include chunk_id with the real value.
5. No tests deleted/weakened: git diff <request-commit>..HEAD -- tests.
Run: python3 -m pytest tests/rag -q (time it); pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps.
