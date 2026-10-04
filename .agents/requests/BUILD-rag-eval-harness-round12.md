# BUILD rag-eval-harness round 12 (builder: MiMo) — 2 fixes

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-eval-harness. Descriptive commits. NEVER delete or weaken existing tests.
Codex review: .agents/codex/VERDICT-rag-eval-harness-review3.md (2 blocking; metrics reference, ticker-off, chunk_id verified).

1. Bootstrap must use the same zero-gold-excluded rows as the overall aggregate (evals/rag_eval/metrics.py:359 vs :328). Share ONE row filter.
   Test: one perfect row + one zero-gold row → overall recall@5 1.0, bootstrap mean 1.0, bootstrap n == 1, zero_gold_excluded == 1.
   Mutation: bootstrap over all answerable rows again → FAILS.
2. No Hugging Face model load in tests/rag: also fake the Verifier's CrossEncoder (api/services/verifier.py:21 construction, :72 eager
   singleton) and tests/rag/test_verifier.py:22. Make the verifier's singleton lazy (no model at import) and inject a deterministic fake in an
   autouse fixture; tests that need specific entailment scores set them explicitly. Add a guard test: run with HF_HUB_OFFLINE=1 and assert no
   `sentence_transformers.CrossEncoder` / `SentenceTransformer` instance is constructed during the suite (patch their __init__ to record and
   fail). Make the dense/hybrid harness tests assert the fake embedding provider was actually used (so reverting the fake to None FAILS them).
   Acceptance: python3 -m pytest tests/rag -q completes in < 60 s here with no model load — report the time and the slowest 5 tests (--durations=5).
Acceptance: all tests pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-eval-harness-round12.md with counts, runtime, mutation outputs. Commit everything.
