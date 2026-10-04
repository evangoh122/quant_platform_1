# CHECK: rag-eval-harness round 12 (checker: DeepSeek)

Read-only. Mutation proofs in /tmp copies. Write .agents/deepseek/VERDICT-rag-eval-harness-round12.md between ===VERDICT START=== /
===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line, counts, mutation results.
Build request: .agents/requests/BUILD-rag-eval-harness-round12.md (from Codex .agents/codex/VERDICT-rag-eval-harness-review3.md). Commit a097865.
Rerun Codex's probes:
1. One perfect row + one zero-gold row → overall recall@5 1.0, bootstrap mean 1.0, bootstrap n == 1, zero_gold_excluded == 1. ONE shared row filter
   for overall and bootstrap. Mutation: bootstrap over all answerable rows → FAILS.
2. No HF model load: verifier lazy (no CrossEncoder at import); autouse fake; guard test fails if a real CrossEncoder/SentenceTransformer is
   constructed (mutation: construct one eagerly in verifier.py at import → guard FAILS). Dense/hybrid harness tests assert the fake embedding
   provider was used (mutation: set the fake to None → those tests FAIL). Time `python3 -m pytest tests/rag -q --durations=5` with HF_HUB_OFFLINE=1.
3. Does the lazy verifier change production behaviour (first-call latency, thread safety of lazy init)? Lazy init must be thread-safe (lock) —
   check.
No tests deleted/weakened (git diff 1c29a3b..HEAD -- tests). pyspark hidden run too (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
