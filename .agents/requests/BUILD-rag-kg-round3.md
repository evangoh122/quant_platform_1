# BUILD: SEC knowledge graph round 3 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit after each fix. NEVER delete or weaken
> existing tests.

DeepSeek check2 (`.agents/deepseek/VERDICT-rag-kg-check2.md`, read it fully), 3 blocking findings:

1. **False chunk-level citations** (`sec_kg/build.py:~128-132`). The accession fallback picks
   `sorted(chunks)[0]` and labels it `citation_level="chunk"`. In 0 of 20 sampled cases the chunk
   contains the fact.
   - REMOVE the arbitrary-chunk fallback.
   - `chunk` level only when the entity's own `source_chunk_id` exists in the corpus, OR when a
     chunk of the same accession verifiably contains the fact. Verify by checking that the chunk
     text contains the value in a normalised form (e.g. 274300000 ↔ "274.3 million" ↔ "274,300") AND
     the period, or the metric's line-item label. Implement a conservative matcher with unit tests.
   - Otherwise use `citation_level="filing"` with `source_url`.
   - Report the new counts. Expect chunk-level to be small, and that's fine.
   - Test: an arbitrary same-filing chunk without the value → filing level.
2. **The production Spark reader reads a non-existent column**
   (`api/services/sec_knowledge_graph.py:~173,220`). It reads `provenance_json`, but the writer
   (`pipelines/build_sec_knowledge_graph.py:~107`) stores `provenance` as `ARRAY<STRUCT>`. So every
   production query returns nothing.
   - Make the writer and reader agree: one schema, one column name. Prefer reading the struct array
     natively.
   - Add a test using fake Row objects shaped EXACTLY like the Delta schema (derive the shape from
     the writer's schema constant), proving `get_fact` returns results through `SparkGraphStore`
     with pyspark hidden.
   - Add a round-trip test: writer schema → reader parse.
3. **Rejection reporting.**
   - `build_graph` must RETURN `BuildStats` with per-reason rejection counts.
   - The manifest reports input rows by entity_type, accepted rows, and rejected rows by reason;
     never node-minus-row arithmetic.
   - The build FAILS (non-zero exit) on any rejection whose reason isn't in a documented allow-list.
   - Test: a malformed row → a counted reason; an unknown-reason path → the build fails.

Re-run the offline build on the real export, and report:
- node/edge counts;
- `citation_level` counts;
- rejections by reason.

Run `python3 -m pytest -q -p no:cacheprovider tests/rag`, and the full suite with
`--ignore=tests/lakebase`. LF line endings only. Don't touch `.agents/dispatch.sh`. Leave no scratch
files. Write `.agents/mimo/VERDICT-rag-kg-round3.md`.
