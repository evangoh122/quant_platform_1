# BUILD rag-kg round 14 (builder: MiMo) — wiring test + line endings

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-kg. Descriptive commits. LF line endings ONLY. NEVER delete or weaken tests.
DeepSeek verdict: .agents/deepseek/VERDICT-rag-kg-round13.md (1 blocking).

1. The migration WIRING is untested: removing the `ensure_concept_norm_column(spark, nodes_table)` call from build() (pipelines/build_sec_knowledge_graph.py
   ~249) leaves all tests green. `test_mutation_skip_alter_test_fails` (tests/rag/test_sec_knowledge_graph.py ~4572) calls the function directly —
   rename it honestly (it's a function test) and ADD a test that runs build() against a fake Spark whose gold_sec_kg_nodes columns lack
   concept_norm and asserts the `ALTER TABLE ... ADD COLUMNS (concept_norm STRING)` SQL is issued BEFORE the MERGE (record call order in one list).
   Mutation (copy via `git archive HEAD | tar -x -C /tmp/<dir>`, paste output): delete the call in build() → the new test FAILS.
2. pipelines/build_sec_knowledge_graph.py has CRLF line endings (git warns). Convert every file you touched in rounds 12–14 to LF; add a test that no
   *.py under sec_kg/, pipelines/, api/services/ and tests/rag/ contains '\r\n'.
Acceptance: python3 -m pytest tests/rag -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-kg-round14.md. Commit everything.
