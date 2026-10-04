===VERDICT START===
# VERDICT: rag-kg-round12 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 12
**Range:** 3428c29..6100382 (HEAD 0e6f4f4, branch slice/rag-kg)

## Blocking findings

1. [tests/rag/test_sec_knowledge_graph.py:4180-4307] Item 2 (P1) Spark-side
   as-of-before-LIMIT predicate is **still not functionally tested** — the required
   mutation proof ("remove the Spark `df.where(F.exists(...))` → FAILS") does not
   hold. I removed the entire `df.where(F.exists(...))` block from
   `SparkGraphStore.find_nodes` (api/services/sec_knowledge_graph.py:462-467) in a
   /tmp copy and ran the suite → **448 passed, 19 skipped** (mutation /tmp/kg12-mut2).
   Zero failures. Two layers of cause:
   - The probe's node ordering is inverted. `build_graph` sorts nodes by `node_id`
     (sec_kg/build.py:875), and for the two XbrlFact rows the **eligible** node
     (value `100`, node_id `90b10ca7…`) sorts **before** the future-only node
     (value `999`, node_id `eca17a1f…`). With `limit=1`, `.limit()` returns the
     eligible row whether or not `F.exists` is applied, so
     `test_spark_limit_1_returns_eligible` passes on both the real and the mutated
     code. The "future-only row followed by an eligible row" precondition is never
     actually created.
   - `test_spark_mutation_remove_exists_filter_fails` (:4283) is not a mutation
     test: it defines `_no_exists_find` (:4290-4293) but never calls it, then calls
     `store.find_nodes` twice (with/without `accepted_before`) asserting only
     `len == 1` — it never removes `F.exists` from the source and never asserts the
     future row is excluded. Net: the P1 predicate remains unguarded, a recurrence
     of the round-11 blocking finding #1.

2. [pipelines/build_sec_knowledge_graph.py:226-237] Item 3 — **no migration for
   pre-round-12 tables.** The new `concept_norm` column is only added via
   `CREATE TABLE IF NOT EXISTS`, which is a no-op against the already-deployed
   `gold_sec_kg_nodes` table (documented in docs/DEPLOYMENT.md:48-49,227). There is
   no `ALTER TABLE … ADD COLUMNS` step (contrast the established pattern in
   pipelines/run_silver_gold.py:107-121 `ensure_model_availability_columns`), so the
   round-12 merge `whenMatchedUpdateAll()` against an existing 6-column table fails
   with a schema mismatch. The query path also does not handle NULL: at
   api/services/sec_knowledge_graph.py:447 `F.col("concept_norm") == norm_concept`
   evaluates NULL for old rows and silently drops them from concept searches.
   **Migration requirement:** add a forward-only, re-runnable
   `ALTER TABLE <catalog>.<schema>.gold_sec_kg_nodes ADD COLUMNS (concept_norm STRING)`
   before the merge (or recreate + full rebuild); a full rebuild then populates
   concept_norm for all matched rows via `whenMatchedUpdateAll`. Without it, either
   the build errors on the existing table or concept queries silently omit legacy rows.

## Item 1 (P1) — concept_norm structured column PASSES

- `concept_norm` computed at build with the same `normalize_unicode()` + `.lower()`
  as the JSONL store (pipelines/build_sec_knowledge_graph.py:198-201), present in the
  StructType (:168), DDL (:232), and docs/DATA_SCHEMAS.md:482 (7 cols).
- Spark query uses exact column equality, no `properties_json` substring for concept
  (api/services/sec_knowledge_graph.py:446-447); grep confirms the only remaining
  `properties_json` substring filters are cik/ticker/period, not concept.
- JSONL store now normalises both sides (api/services/sec_knowledge_graph.py:186).
- Parity harness (TestConceptNormParity, 7 tests) covers `a"b`, backslash,
  full-width `Ｒｅｖｅｎｕｅ`, injection `revenue","metric":"netincome` (0 matches),
  `revenue` vs `revenues` (0 matches), metric-field fallback — all green on BOTH stores.
- Mutation proof holds: reverting Spark concept match to the JSON substring
  (/tmp/kg12-mut1) → **3 failed** (test_escaped_quote_concept, test_backslash_concept,
  test_mutation_spark_json_substring_fails), 445 passed.

## Non-blocking notes

3. Fake Spark infra for item 2 is itself correct: `F.exists` now builds a real
   `_Expr("exists", col, lambda)` (tests/rag/test_sec_knowledge_graph.py:1587) and
   `_eval` evaluates it over provenance elements (:1539-1541) and raises `ValueError`
   on unknown ops / bare expressions (:1542-1545). The `TestPredicatePushdown` variant
   (:2884-2888) was updated in kind. Only the probe data ordering defeats the mutation.

## Checks run

- `python3 -m pytest tests/rag -q` → **448 passed, 19 skipped, 1 warning**
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **448 passed, 19 skipped**
- Mutation 1 (concept → JSON substring, /tmp/kg12-mut1) → **3 failed** (proof holds)
- Mutation 2 (remove Spark `F.exists`, /tmp/kg12-mut2) → **448 passed, 0 failed** (proof FAILS)
- `grep concept_norm docs/DATA_SCHEMAS.md` → line 482 present
- `grep properties_json api/services/sec_knowledge_graph.py` → no concept substring remains
===VERDICT END===
