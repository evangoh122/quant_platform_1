# CHECK: rag-kg round 10 (checker: DeepSeek)

Read-only for source. Mutation proofs in /tmp copies (cp -r to /tmp/kg10-mut-*). Write .agents/deepseek/VERDICT-rag-kg-round10.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line, counts, mutation results.
Build request: .agents/requests/BUILD-rag-kg-round10.md (from your round-9 verdict). Commits: 625e8b4..HEAD (note commit c738f1d has an empty
message "fix:" — note it).
Verify:
1. Query pushdown: get_fact / facts_timeseries / risk_factors use filtered accessors that apply Spark `.where()` column-expression predicates
   (no string-built SQL) for ticker/cik + concept + period + as-of and a hard `.limit()` BEFORE collect/toLocalIterator; edges fetched by a
   bounded node-id set. Spy tests assert predicates + limit and that no unfiltered DataFrame is collected. Mutation: make get_fact call the
   unfiltered iter_nodes() → FAILS.
2. TZ test: MiMo describes it as "proves naive .timestamp() gives wrong epoch" — that only demonstrates the bug. The requirement is that the
   test runs the PIPELINE's real timestamp conversion under TZ=Asia/Singapore and asserts the exact UTC epoch. Check which it is. Mutation:
   restore naive `.timestamp()` in pipelines/build_sec_knowledge_graph.py → THIS test must fail with a TZ assertion.
3. build() with subset_filter raises before any delete; test exists. Deleted/existing counts logged.
4. Docstring fixed.
5. No tests deleted/weakened: git diff 625e8b4..HEAD -- tests.
Run: python3 -m pytest tests/rag -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps.
