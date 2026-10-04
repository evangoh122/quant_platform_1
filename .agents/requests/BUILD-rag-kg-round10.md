# BUILD rag-kg round 10 (builder: MiMo)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-kg. Descriptive commits. NEVER delete or weaken existing tests.
DeepSeek verdict: .agents/deepseek/VERDICT-rag-kg-round9.md (CHANGES_REQUESTED). Items 2–5 of round 9 verified.

1 (blocking). Query predicate pushdown. api/services/sec_knowledge_graph.py:168-237 `SparkGraphStore.iter_nodes()/iter_edges()` scan the whole
   table via toLocalIterator; get_fact (:371), facts_timeseries (:473), risk_factors (:536) filter in Python afterwards.
   Add filtered accessors (e.g. `find_nodes(node_type, cik=None, ticker=None, concept=None, period_start=None, period_end=None,
   accepted_before=None, limit=...)`) that apply `.where()` predicates in Spark (column expressions, no string-built SQL — no injection) and a
   hard `.limit(n)` BEFORE collecting; edges by node-id set with a bounded IN / join. Make the query methods use them; keep the in-memory
   store implementing the same interface for tests.
   Tests with fake Spark: a spy DataFrame records `.where`/`.filter` predicates and `.limit`; assert get_fact / facts_timeseries / risk_factors
   push ticker/cik + concept + as-of predicates and a limit, and that collect()/toLocalIterator() is never called on an unfiltered DataFrame.
   Mutation proof (in /tmp copy, paste output): make get_fact call the unfiltered iter_nodes() again → test FAILS.
2. Real TZ regression test. Replace the placeholder `test_naive_datetime_to_epoch_tz_dependent` with a test that sets
   `monkeypatch.setenv("TZ", "Asia/Singapore"); time.tzset()` (restore + tzset on teardown), runs the pipeline's real timestamp conversion on
   a known UTC instant, and asserts the exact epoch. Mutation: restore naive `.timestamp()` → THIS test fails with a TZ assertion.
   Skip only on platforms without time.tzset (Windows) with a clear reason.
3. Full-rebuild delete safety: log the number of deleted nodes/edges per run (and add them to the manifest only if you add documented
   columns — optional). Add a guard: if build() is ever called with a subset filter, refuse to issue the unscoped delete (raise) — test it.
4. Fix the docstring claiming "274.3 million ↔ 274300000" scale-word matching (feature doesn't exist) — make it accurate.
Acceptance: python3 -m pytest tests/rag -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-kg-round10.md with counts + mutation outputs. Commit everything.
