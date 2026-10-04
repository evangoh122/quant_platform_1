===VERDICT START===
# VERDICT: rag-kg-round10 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 10
**Range:** 625e8b4..HEAD (code in c738f1d "fix:" — empty message body, noted; agent-only commits 6ad708d, c19fa5a)

## Blocking findings

1. [tests/rag/test_sec_knowledge_graph.py:3084-3133] Item #2 TZ regression test does not
   test the PIPELINE. `TestTimezoneRegression::test_singapore_tz_affects_naive_timestamp`
   only sets `TZ=Asia/Singapore` + `time.tzset()`, then asserts `naive.timestamp()` on
   **locally-constructed** `datetime` objects (`datetime(2023,11,15,6,13,20)`,
   `datetime(2023,11,14,22,13,20)`). It never imports or invokes
   `pipelines/build_sec_knowledge_graph.py` (nor `sec_kg/`) timestamp conversion, and
   asserts nothing about the pipeline's produced epoch. The build request required the
   test to "run the pipeline's real timestamp conversion on a known UTC instant and
   assert the exact epoch", with the mutation "restore naive `.timestamp()` → THIS test
   fails with a TZ assertion." That mutation does NOT fail this test:
   - Mutation (in /tmp/kg10-mut-tz): reverted `pipelines/build_sec_knowledge_graph.py:70`
     and `:90` back to `int(row.accepted_ts.timestamp())` (naive `.timestamp()`).
   - `TestTimezoneRegression::test_singapore_tz_affects_naive_timestamp` → **1 passed**
     (still green).
   - The only failures are 6 `AttributeError: '_FakeRow' object has no attribute
     'accepted_ts'` in `TestPipelineValidation`/`TestSubsetFilterDeleteSafety` — an
     incidental fake-row schema mismatch, not a TZ assertion. The guard is not the
     requested proof; the test is the "demonstrates the bug" variant, not a pipeline
     regression. → CHANGES_REQUESTED.

## Non-blocking notes

2. [api/services/sec_knowledge_graph.py:474-480] `accepted_before` (as-of) is applied
   **post-collect** on the per-node provenance array, not pushed into Spark `.where()`.
   node_type / ticker / cik / concept / period_start / period_end ARE pushed (lines
   435-456) and `.limit()` is before collect (line 459), so the high-selectivity filters
   and the round-9 full-scan defect are fixed. But the CHECK item 1 enumerates "as-of"
   among the pushed predicates; it is not pushed. Correct and bounded (filter runs on the
   already-limited result), so non-blocking, but note the deviation.

3. [api/services/sec_knowledge_graph.py:492] `find_edges_by_node_ids` is added to the
   `Protocol` (:46), `JsonlGraphStore` (:202), and `SparkGraphStore` (:492) but is **never
   called** anywhere (grep of the source shows zero call sites). Edges in `get_fact` are
   still fetched via `get_edges_for_node` (single node-id predicate, already bounded).
   Dead code — fine, but the "edges by bounded node-id set" path is not actually exercised
   by any query.

4. [pipelines/build_sec_knowledge_graph.py:257-261] The logged "Stale rows cleaned:
   ~{existing_node_count}" is **not** the deleted count — `deleted_nodes_est =
   max(0, existing_node_count)` is the pre-existing row count, mislabeled as deletions.
   The actual `whenNotMatchedBySourceDelete` deletion count is never computed (would need a
   post-merge recount). The "existing" count IS logged accurately (line 237-238), but the
   "deleted" figure is fabricated. Item #3 asked to "log the number of deleted nodes/edges
   per run"; the number logged is not that number.

5. [pipelines/build_sec_knowledge_graph.py:229] The `subset_filter` guard is correctly
   placed before `whenNotMatchedBySourceDelete` (line 242/248) and is tested
   (`test_subset_filter_raises`, `test_no_subset_filter_succeeds`), so no unscoped delete
   can fire on a partial rebuild. However it runs AFTER the full silver read + graph build +
   `CREATE TABLE IF NOT EXISTS`, so a subset-filter call still wastes a full build and may
   create empty tables before raising. Safety property holds; guard could be earlier.

6. [api/services/sec_knowledge_graph.py:438-456] `find_nodes` uses
   `F.col("properties_json").contains(f'"cik":"{cik}"')` — string interpolation into a
   **column-expression literal**, not SQL, so no SQL-injection vector. Matching relies on
   `deterministic_json` compact form (`separators=(",",":")`, `sort_keys=True`,
   `sec_kg/model.py:339`), which the tests confirm. Edge case: a cik/ticker/concept
   containing `"` or `\` would break the JSON-key substring match (correctness, not
   injection) — inputs are normalized/allow-listed upstream.

7. Commit `c738f1d` has an empty message body ("fix:" only). Cosmetic; noted per CHECK.

## Counts (reproduced independently)

- `python3 -m pytest tests/rag -q` → **427 passed, 19 skipped, 0 failed**, 1 warning.
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **427 passed, 19 skipped, 0 failed**, 1 warning.

## Mutation proofs (fresh `/tmp/kg10-mut-*` copies)

- Mutation 1 — get_fact calls unfiltered `iter_nodes()` instead of `find_nodes()`
  (/tmp/kg10-mut-pushdown) → **3 FAILED** (`test_get_fact_pushes_ticker_and_period_predicates`,
  `test_collect_never_called_on_unfiltered_dataframe`,
  `test_mutation_unfiltered_iter_nodes_fails` with "got 2" where-calls), 2 passed. Detected. ✓
- Mutation 2 — restore naive `.timestamp()` in `pipelines/build_sec_knowledge_graph.py`
  (/tmp/kg10-mut-tz) → **6 FAILED** (`TestPipelineValidation` ×4,
  `TestSubsetFilterDeleteSafety` ×2, all `AttributeError: '_FakeRow' has no attribute
  'accepted_ts'`); **`TestTimezoneRegression::test_singapore_tz_affects_naive_timestamp`
  still PASSED**. The TZ test does NOT catch the regression (see blocking finding 1). ✗

## Checks run

- `git log --oneline -20` / `git status` / `git branch -a` → on `slice/rag-kg`, HEAD `c19fa5a`, ahead of origin by 23.
- `git diff 625e8b4..HEAD --stat` → 6 files, +894/-30 (2 source, 1 pipeline, 1 test, 2 agent files).
- `git show c738f1d --stat` → 4 files, +829/-30 (empty message body).
- `git diff 625e8b4..HEAD -- tests | grep -E '^\-' | grep -E 'def test_|class Test'` → 0 (no test deleted/weakened; 18 test defs added; only removed test lines are a docstring and a trailing `)`).
- grep `.timestamp()` in sec_kg/, pipelines/, api/services/sec_knowledge_graph.py → only aware-datetime `as_of.timestamp()` uses (lines 380, 522 in api/services; tools_retrieval.py:159, db/lakebase.py:79), no naive `.timestamp()` in the lane.
- grep `find_edges_by_node_ids` call sites → 0 (dead code, note 3).
- `python3 -m pytest tests/rag -q` → pass (427).
- pyspark-hidden shim run → pass (427).
===VERDICT END===
