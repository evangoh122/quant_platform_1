# VERDICT: rag-kg-round11 — MiMo
**Status:** APPROVED
**Round:** 11

## Blocking findings
(none)

## Non-blocking notes
- SparkGraphStore as-of filter uses `F.exists(col("provenance"), lambda p: p["accepted_epoch"] <= as_of_epoch)` which requires Spark 3.4+ for higher-order array functions. The JsonlGraphStore parity test verifies correctness without Spark.
- The driver memory cap (max_entities=2M) is a safety net, not a scaling solution. At current scale (~63.5k nodes / ~137k edges), driver memory is not a concern.
- The `_setup_pyspark_mocks` now returns `_table_data` as a third element — all 16 call sites updated.

## Checks run
- `python3 -m pytest tests/rag -q` → **133 passed** in 8.45s
- `git diff --stat` → 3 files changed, 661 insertions(+), 41 deletions(-)

## Implementation details

### Item 1 (P1): LIMIT before as-of
- `api/services/sec_knowledge_graph.py:458-480`: Added `F.exists()` predicate on provenance array BEFORE `.limit()`. Post-collect filter still keeps only eligible provenance entries.
- Test: `TestLimitBeforeAsOf::test_limit_1_returns_eligible_not_future` — future-only row + eligible row, limit=1 → returns eligible.
- Mutation: without the Spark-side filter, limit=1 could return the future row (filtered out post-collect → 0 results).

### Item 2 (P1): Case-insensitive concept matching
- `api/services/sec_knowledge_graph.py:443-448`: Changed from exact-case `contains(f'"entity_key":"{concept}"')` to `F.lower(F.col("properties_json")).contains(f'"entity_key":"{lowered}"')` with `|` for metric field.
- Test: `TestCaseInsensitiveConceptMatching` — `revenues`, `Revenues`, `REVENUES`, `rEvEnUeS` all return the same nodes on JsonlGraphStore (parity test).
- Spark test infrastructure: Added `_LoweredCol` class and `lower_contains` eval op in `TestSparkGraphStoreRoundTrip._eval` and `TestPredicatePushdown._eval_condition`.

### Item 3 (P2): Driver memory cap
- `pipelines/build_sec_knowledge_graph.py`: Added `max_entities: int = 2_000_000` parameter. Raises `MemoryError` when `len(chunk_metadata) + len(entities) > max_entities`.
- Updated module docstring to document driver-bound design.
- Removed misleading "avoid driver-wide collect" comments (lines 66, 86).
- Test: `TestDriverMemoryCap::test_cap_raises_on_overflow` (max_entities=5 with 6 entities → MemoryError), `test_cap_default_allows_small_dataset`, `test_mutation_no_cap_allows_overflow`.

### Item 4 (P2): Functional stale-delete test
- Replaced §29 source-grep tests with §39 `TestFunctionalStaleDelete`:
  - `test_merge_calls_when_not_matched_by_source_delete`: verifies 2 calls (nodes + edges)
  - `test_stale_row_removed_on_second_build`: run 1 with 2 entities (7 nodes), run 2 with 1 entity → nodes count decreases
  - `test_mutation_remove_delete_fails`: no-op delete → stale nodes persist (count doesn't decrease)
- Fixed `_setup_pyspark_mocks.createDataFrame` to convert tuples to named `_FakeRow` using schema field names.
- Fixed `_FakeDeltaTable` subclasses: `alias()` instead of `as_()`.