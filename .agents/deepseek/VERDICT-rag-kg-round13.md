===VERDICT START===
# VERDICT: rag-kg-round13 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 13
**Range:** c85169f (migration + NULL guard) + f609f7a (as-of fixture reorder), on 0e6f4f4..HEAD (branch slice/rag-kg)

## Blocking findings

1. [pipelines/build_sec_knowledge_graph.py:249 vs tests/rag/test_sec_knowledge_graph.py:4572-4590]
   Item 2 mutation proof **"skip the ALTER → FAILS" does not hold.** Removing the
   `ensure_concept_norm_column(spark, nodes_table)` call from `build()` (the real
   regression: a pre-round-12 table never gets the column, so the MERGE then fails
   on schema mismatch) leaves the entire suite green — **455 passed, 19 skipped,
   0 failed** (mutation /tmp/deepseek-r13-mut2). The claimed mutation test
   `test_mutation_skip_alter_test_fails` (:4572) is not a mutation test: it
   imports and calls `ensure_concept_norm_column` *directly* (:4585), never
   invoking `build()`, so it passes whether or not `build()` is wired to the
   migration. Its docstring ("This test verifies that ensure_concept_norm_column
   is called in the build", :4575) is false. The function-level tests are sound —
   removing the `spark.sql("ALTER TABLE …")` line instead yields **3 failed**
   (`test_alter_issued_when_column_missing`, `test_idempotent_second_call`,
   `test_mutation_skip_alter_test_fails`, /tmp/deepseek-r13-mut3) — but the
   *wiring* of the migration into `build()` before the MERGE is unguarded. Add a
   test that runs `build()` against a fake Spark whose `gold_sec_kg_nodes.table().columns`
   lacks `concept_norm` and asserts an `ADD COLUMNS` SQL is issued before the MERGE.

## Item 1 (P1) — re-run round-12 mutation 1: PASSES (round-12 finding #1 resolved)

- f609f7a now sorts the fixture so the future-only node leads
  (`node_rows.sort(key=…future-only first)`, tests/rag/test_sec_knowledge_graph.py:4279-4283,
  with an explicit assert the first row is future-only).
- Removing the Spark `df.where(F.exists(...))` block
  (api/services/sec_knowledge_graph.py:471-479) → `test_spark_limit_1_returns_eligible`
  **FAILS** (0 results instead of eligible row) and `test_spark_mutation_remove_exists_filter_fails`
  fails too (/tmp/deepseek-r13-mut1). The P1 as-of-before-LIMIT predicate is now
  functionally guarded.

## Item 2 (P0) — ensure_concept_norm_column: function correct, wiring unguarded

- ALTER only when missing / no-op when present / idempotent: covered by
  `test_alter_issued_when_column_missing`, `test_no_alter_when_column_exists`,
  `test_idempotent_second_call`, `test_unreadable_table_skips` — green.
- Called before the MERGE: `ensure_concept_norm_column(spark, nodes_table)` at
  pipelines/build_sec_knowledge_graph.py:249 precedes `CREATE TABLE IF NOT EXISTS`
  (:252) and `DeltaTable…merge(…whenMatchedUpdateAll()…)` (:298-302). Fresh tables get
  the column via the DDL (:258); pre-existing tables via the ALTER.
- MERGE populates `concept_norm` on matched rows: `nodes_df` carries `concept_norm`
  (:224-227) and `whenMatchedUpdateAll()` updates every matched row, so a full
  rebuild backfills legacy rows. Confirmed by inspection.
- Only gap: the mutation proof above (Blocking #1).

## Item 3 (P1) — NULL concept_norm handling: PASSES

- MiMo picked the **"rebuild required" fail-fast error** option: `find_nodes`
  raises `RuntimeError` when any row of the (node_type-filtered) result has NULL
  `concept_norm` (api/services/sec_knowledge_graph.py:447-458), rather than
  silently dropping legacy rows.
- No substring matching reintroduced: concept still uses exact column equality
  `F.col("concept_norm") == norm_concept` (:459); grep shows no
  `properties_json`/`contains`/`get_json_object` for concept.
- Tests exist and pass: `test_null_concept_norm_raises_error`,
  `test_no_error_when_concept_norm_populated` (fake `where` really filters via
  `_eval` "is_null" op, `_FakeCol.isNull`, `_FakeDataFrame.count`).
- Documented in docs/DEPLOYMENT.md:270-290 (migration + NULL handling + operator action).

## No tests deleted/weakened

- c85169f: `12 0` api, `22 0` docs, `26 0` pipelines, `277 0` tests (all additions).
- f609f7a: `6 0` tests (all additions). Nothing deleted or weakened.

## Checks run

- `python3 -m pytest tests/rag -q` (clean /tmp archive of HEAD) → **455 passed, 19 skipped, 1 warning**
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **455 passed, 19 skipped**
- Mutation 1 (remove Spark `F.exists` where) → **2 failed** (`test_spark_limit_1_returns_eligible`, `test_spark_mutation_remove_exists_filter_fails`)
- Mutation 2 (remove `ensure_concept_norm_column(...)` call from `build()`) → **455 passed, 0 failed** (proof FAILS)
- Mutation 3 (remove `spark.sql("ALTER TABLE …")` line) → **3 failed** (function-level guard holds)
- `grep concept_norm docs/DEPLOYMENT.md` → lines 270-290 present
- `grep 'concept' api/services/sec_knowledge_graph.py` → no substring/contains/get_json_object for concept
===VERDICT END===
