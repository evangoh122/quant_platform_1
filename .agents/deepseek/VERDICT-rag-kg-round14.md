===VERDICT START===
# VERDICT: rag-kg-round14 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 14
**Range:** d5c5daa (fix(kg): round 14) on slice/rag-kg, tests/rag/test_sec_knowledge_graph.py (+168/-19)

## Blocking findings

(none)

## Round-13 blocking finding #1 — now RESOLVED

Round 13 required a real `build()` wiring test that runs against a fake Spark
whose `gold_sec_kg_nodes` lacks `concept_norm` and asserts an `ADD COLUMNS`
(concept_norm) SQL is issued before the MERGE. This is now present as
`TestConceptNormMigration::test_build_issues_alter_before_merge`
(tests/rag/test_sec_knowledge_graph.py:4468):

- Sets `table_data["gold_sec_kg_nodes"]` to a pre-round-12 row **without**
  `concept_norm`, wraps `fake_spark.sql` and `DeltaTable.forName` to record a
  single ordered `call_order` list, calls `pipeline_mod.build(...)`, and asserts
  `alter_indices[0] < merge_indices[0]`.
- **My mutation proof holds**: deleting the
  `ensure_concept_norm_column(spark, nodes_table)` call at
  pipelines/build_sec_knowledge_graph.py:249 (commenting the line) → the test
  FAILS with `AssertionError: ALTER TABLE ADD COLUMNS (concept_norm) not found
  in call order` (assert 0 >= 1). Restored → passes. The migration is now
  genuinely guarded at the wiring level, not just at the function level.

## Misnamed test renamed honestly

The old `test_mutation_skip_alter_test_fails` (round 13) — which imported and
called `ensure_concept_norm_column` directly and never invoked `build()`, while
its docstring falsely claimed to verify `build()` wiring — is removed. It is
replaced by `test_ensure_concept_norm_column_issues_alter`
(tests/rag/test_sec_knowledge_graph.py:4448), now correctly named and scoped as
a *function-level* test (calls the function directly, asserts exactly 1 ALTER),
with an honest docstring. Body is identical to the old test; no coverage lost.

## CRLF guard (item 2)

`TestLineEndings::test_no_crlf_in_python_files` (tests/rag/test_sec_knowledge_graph.py:2815)
walks `sec_kg/`, `pipelines/`, `api/services/`, `tests/rag/` for `*.py` and
asserts no `b"\r\n"`. No CRLF present in HEAD. **Mutation proof**: writing a
`tests/rag/_crlf_probe.py` with CRLF → test FAILS listing the probe file.
Removed probe → passes. Guard is real.

## No tests deleted/weakened

- Diff is +168/-19 in the test file. The only removed test is the misnamed
  `test_mutation_skip_alter_test_fails`; its replacement `test_ensure_concept_norm_column_issues_alter`
  is byte-equivalent in body. Net suite grew 455 → 457 (renamed +1, wiring +1,
  CRLF +1, old removed -1).
- `_FakeDataFrame.columns` property (tests/rag/test_sec_knowledge_graph.py:2049)
  added to support `ensure_concept_norm_column` reading `.columns`; additive.

## Non-blocking notes

- tests/rag/test_sec_knowledge_graph.py:2809: closing `)` of `pytest.fail(...)`
  in `TestNoDriverWideCollects::test_build_uses_to_local_iterator` was dedented
  from 20 to 8 spaces. Purely cosmetic — the parenthesis still closes the same
  `pytest.fail` call and the assertion fires identically. Likely an accidental
  editor artifact; recommend restoring indentation but it does not change
  behaviour or weaken the test.
- `ensure_concept_norm_column` still interpolates `fqn` into `ALTER TABLE {fqn}`
  (pipelines/build_sec_knowledge_graph.py:54). `fqn` is a trusted internal
  `catalog.schema.table` identifier (not user input), and DDL identifiers cannot
  be parameterized — not an injection vector. Unchanged from prior rounds.

## Checks run

- `python3 -m pytest tests/rag -q` (clean /tmp archive of HEAD) → **457 passed, 19 skipped, 1 warning**
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **457 passed, 19 skipped**
- `... pytest tests/rag/test_sec_knowledge_graph.py::TestConceptNormMigration tests/rag/test_sec_knowledge_graph.py::TestLineEndings -v` → **7 passed**
- Mutation (comment `ensure_concept_norm_column(spark, nodes_table)` in build()) → `test_build_issues_alter_before_merge` **FAILS** (`assert 0 >= 1`; ALTER absent from call order); other 5 TestConceptNormMigration tests pass
- Mutation (introduce CRLF probe file under tests/rag) → `test_no_crlf_in_python_files` **FAILS** listing the probe
- `grep -rlP '\r' sec_kg pipelines api/services tests/rag --include='*.py'` → no matches (no CRLF)
===VERDICT END===
