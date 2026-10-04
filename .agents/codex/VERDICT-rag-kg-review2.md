===VERDICT START===
# VERDICT: rag-kg — Codex review
Status: CHANGES_REQUESTED

## Findings

1. **[P1] Spark timestamps remain dependent on the driver timezone.**  
   `pipelines/build_sec_knowledge_graph.py:59` and `:73` call `.timestamp()` directly on Spark-returned datetimes. With `TZ=Asia/Singapore`, a naïve `2023-11-14T22:13:20` became `2023-11-14T14:13:20+00:00`. This shifts `accepted_ts`, provenance, and `valid_from` eight hours earlier, allowing facts to appear before acceptance.

2. **[P1] `facts_timeseries` does not apply restatement selection.**  
   `api/services/sec_knowledge_graph.py:464-498` returns every eligible fact version without deduplicating by logical series after PIT filtering. A two-version reproduction returned both `100` and restated `110`; the specification requires only the latest eligible version per series.

3. **[P1] Chunk citation verification can certify the wrong numeric value.**  
   `sec_kg/build.py:127-175` converts XBRL values and filing text numbers to `float`. Precision loss caused `_chunk_text_matches_value("Assets were 9007199254740992", "9007199254740993", ..., "Assets")` to return `True`, producing an incorrect chunk-level citation. Citation comparison must remain lossless, such as with `Decimal`.

4. **[P1] Full rebuilds retain stale graph rows.**  
   `pipelines/build_sec_knowledge_graph.py:199-214` only updates/inserts by ID. It never deletes rows absent from the current input universe, so removed or newly rejected facts and edges remain queryable indefinitely.

5. **[P2] Agent inputs are not fully bounded or allow-listed.**  
   `agent/tools_retrieval.py:223-226` specifies no maximum length for `metric` or `period`, and `:251-254` calls `normalize_symbol`, which only performs regex validation at `agent/guardrails.py:43-53`; it does not consult the configured allow-list. A non-allow-listed ticker and a one-million-character metric reached the backend.

6. **[P2] Production build/query paths collect whole tables to the driver.**  
   `pipelines/build_sec_knowledge_graph.py:48-67` collects all source chunks and entities, while `api/services/sec_knowledge_graph.py:168-203` collects every graph node for each fact query. This violates the required predicate pushdown and no-driver-wide-collect constraints.

## Tests

- `python3 -m pytest tests/rag -q`
- Result: **392 passed, 19 skipped, 1 warning** in 96.62s.

## Mutation results

1. Inverted the `get_fact` PIT eligibility guard in `/tmp/kg-review-mut-pit`: **2 failed, 6 passed**.
2. Bypassed conservative citation-content verification in `/tmp/kg-review-mut-citation`: **1 failed, 4 passed**.
3. Bypassed `validate_and_raise` in `/tmp/kg-review-mut-validation`: **1 failed**.

The repository worktree remained unchanged.
===VERDICT END===
