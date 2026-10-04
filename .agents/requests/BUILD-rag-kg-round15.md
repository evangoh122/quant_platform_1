# BUILD rag-kg round 15 (builder: MiMo)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-kg. Descriptive commits. LF only. NEVER delete or weaken tests.
Reviewer verdict: .agents/reviewer/VERDICT-rag-kg-r4.md (1×P1, 2×P2, 1×P3). Each fix needs a test that FAILS on the old code — prove it in a copy made
with `git archive HEAD | tar -x -C /tmp/<dir>` and paste the output.

1 (P1, confirmed by Claude). api/services/sec_knowledge_graph.py find_nodes (~416-432) `.select(...)` omits `concept_norm`, but the NULL guard and the
   equality filter use F.col("concept_norm") → UNRESOLVED_COLUMN on real Spark for every concept search. Add "concept_norm" to the select (and any
   other column filtered after the select — audit every F.col() used after a .select in this file). The mock DataFrames' `select()` returns self
   (test file ~1495, ~2054, ~2858), hiding this: make the fake `select()` really PROJECT (keep only the named columns/aliases) and make referencing a
   non-projected column RAISE. Mutation: remove concept_norm from the select → a concept-search test FAILS.
2 (P2). pipelines/build_sec_knowledge_graph.py ~150-156: max_entities is checked AFTER collecting into driver memory. Count the source tables first
   (df.count() on the filtered source) and raise before collecting; fix the docstring. Test: count over cap → raises and toLocalIterator/collect never
   called (spy).
3 (P2). The NULL-concept guard raises "full rebuild required" for nodes whose concept is legitimately empty. Limit it to legacy rows (nodes of a
   concept-bearing type — XbrlFact/Metric — whose properties have a non-empty entity_key/metric but concept_norm IS NULL). Test both cases.
4 (P3). agent/tools_retrieval.py query_sec_facts: allow-list `metric` against the known concept vocabulary (or a validated pattern for XBRL concept
   names) and `period` against the accepted formats (YYYY, YYYY-Qn, YYYY-MM-DD..YYYY-MM-DD — whatever the spec uses); reject before the backend.
Acceptance: python3 -m pytest tests/rag -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-kg-round15.md. Commit everything.
