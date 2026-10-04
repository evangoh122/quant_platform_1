===VERDICT START===
# VERDICT: rag-kg-r3 — Codex review
Status: CHANGES_REQUESTED

## Findings

1. **[P1] LIMIT can discard all as-of-eligible nodes.**  
   `api/services/sec_knowledge_graph.py:458-480` applies `.limit(limit)` before filtering provenance by `accepted_before`. An adversarial probe with a future-only row followed by an eligible row and `limit=1` returned `[]` instead of the eligible row. The as-of predicate must be applied in Spark before LIMIT.

2. **[P1] Concept pushdown is case-sensitive and changes query behavior.**  
   `api/services/sec_knowledge_graph.py:443-448` uses case-sensitive JSON substring matching, while `JsonlGraphStore.find_nodes()` compares concepts case-insensitively at `:184-187`. Production Spark probing returned a result for `Revenues` but none for `revenues`, contrary to the prior API behavior.

3. **[P2] The build still materializes whole source tables in driver memory.**  
   `pipelines/build_sec_knowledge_graph.py:67-120` streams rows through `toLocalIterator()` but accumulates every section in `chunk_metadata` and every entity in `entities`. It then materializes complete `nodes_data` and `edges_data` lists at `:162-189`. This remains an unbounded driver-wide build, only replacing `.collect()` with incremental transfer.

4. **[P2] The checked-in stale-delete mutation test does not detect removal of the delete behavior.**  
   `tests/rag/test_sec_knowledge_graph.py:2670-2686` searches source text for `whenNotMatchedBySourceDelete`. Removing both actual method calls while leaving comments and error text made all four stale-delete/subset tests pass. A temporary functional fake-Delta test passed current code and failed the behavior-only mutant.

## Requested probes

- Pipeline under `TZ=Asia/Singapore`: exact epoch preserved.
- Restatement: between versions returned `100`; after both returned only `110`.
- Citation: `9007199254740992` did not match `9007199254740993`; exact value matched.
- Full rebuild removed stale IDs; subset rebuild was rejected.
- Non-allow-listed ticker and 1,000,000-character metric were rejected with zero backend calls.
- Query predicates and LIMIT were applied before collection.
- Adversarial as-of/LIMIT probe: **failed**, returning no eligible row.

## Tests and mutations

- `python3 -m pytest tests/rag -q`  
  **428 passed, 19 skipped, 1 warning**.
- Six-finding focused suite: **26 passed**.
- `/tmp` mutations:
  - Naive timestamp conversion: **1 failed** with the expected eight-hour shift.
  - Removed restatement dedupe: **2 failed**.
  - Reverted citation comparison to float: **3 failed**.
  - Removed input bounds/allow-list: both hostile inputs reached the backend.
  - Reverted `get_fact` to unfiltered iteration: **3 failed**.
  - Removed stale-delete calls: checked-in tests incorrectly passed; temporary functional test failed.

Repository remained unchanged; `git status --short` was empty at HEAD `68d51f0`.
===VERDICT END===
