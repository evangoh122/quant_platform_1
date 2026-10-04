# BUILD rag-kg round 8 (builder: MiMo) — small, test-only round

> CONTINUATION: your previous run stopped mid-task. Your partial edits are committed as the latest "wip(kg): round 8 partial" commit. Run `git show HEAD`, finish every item below, run the mutation proofs, write the verdict and commit. Do not start over.


IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-kg. Commit with descriptive messages.
NEVER delete or weaken existing tests. Checker verdict: .agents/deepseek/VERDICT-rag-kg-round7.md. Production code is fine.

1 (blocking). Test (b) (tests/rag/test_sec_knowledge_graph.py ~2299-2309) never asserts order — the loop ends in `pass`
   and the validate marker lives in a separate list. Record a "validate" entry INTO write_spy.calls (wrap validate_and_raise
   with a spy that appends to the same list) and assert its index < the index of the first write/createDataFrame/sql call.
   Mutation proof in /tmp copy: move the validate_and_raise call after the writes in pipelines/build_sec_knowledge_graph.py
   → test (b) FAILS (not only test (a)). Paste output.
2 (blocking). Schema test (~2375-2415) checks only count + names. Assert per-field dataType AND nullable against the
   documented schema (docs/DATA_SCHEMAS.md ~498-507); make the fake _MapType keep valueContainsNull and compare it.
   Mutation proof: IntegerType → LongType for one field in pipelines/build_sec_knowledge_graph.py ~236-246 → FAILS.
3. Mutation A (validate_and_raise replaced by a dict) currently fails 2 tests; make test (c) also fail under it if feasible
   (e.g. assert the manifest's validation-derived fields), otherwise say why not.

Acceptance: python -m pytest tests/rag -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) all pass.
.agents/mimo/VERDICT-rag-kg-round8.md with counts + mutation outputs. Commit everything.
