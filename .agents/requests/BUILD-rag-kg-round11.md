# BUILD rag-kg round 11 (builder: MiMo; checker: DeepSeek; reviewer: Codex)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-kg. Commit after each item, descriptive messages.
NEVER delete or weaken existing tests (item 4 replaces a source-grep test with a functional one — allowed, say so).
Codex review: .agents/codex/VERDICT-rag-kg-review3.md (2×P1, 2×P2).

1 (P1). LIMIT before as-of (api/services/sec_knowledge_graph.py:458-480): push the as-of predicate into Spark BEFORE .limit(). If provenance is an
   array of accepted_ts values, filter with a Spark higher-order expression (e.g. `F.exists(col("provenance"), lambda p: p.accepted_ts <= as_of)`
   or the stored min accepted_ts column) so ineligible rows never consume the limit. Test: Codex's probe — a future-only row followed by an
   eligible row, limit=1 → returns the eligible row. Mutation: move as-of back after limit → FAILS.
2 (P1). Concept matching must be case-insensitive in Spark (:443-448) like JsonlGraphStore (:184-187): compare lower(concept) to lower(input)
   on a structured field, not a JSON substring. Test: `revenues` and `Revenues` return the same nodes on the Spark store (fake Spark that
   evaluates the predicate) AND on the JSONL store (parity test).
3 (P2). Build driver memory (pipelines/build_sec_knowledge_graph.py:67-120, :162-189). Current scale: ~63.5k nodes / ~137k edges — fits a driver.
   Claude's decision: do NOT rewrite into a distributed build now. Instead: (a) a configurable hard cap (e.g. max_entities default 2,000,000) that
   raises a clear error before OOM, (b) document the driver-bound design and the cap in docs + the module docstring, (c) a test that the cap
   raises. Remove the claim anywhere that the build is "no driver-wide collect".
4 (P2). Replace the source-grep stale-delete test (tests/rag/test_sec_knowledge_graph.py:2670-2686) with a FUNCTIONAL fake-Delta test: a fake
   DeltaTable MERGE builder that records whenNotMatchedBySourceDelete() calls and applies them to an in-memory table; run build twice where run 2
   lacks a node → that node is deleted. Mutation: remove the actual whenNotMatchedBySourceDelete() calls (leave comments) → FAILS.
Acceptance: python3 -m pytest tests/rag -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-kg-round11.md with counts + mutation outputs. Commit everything.
