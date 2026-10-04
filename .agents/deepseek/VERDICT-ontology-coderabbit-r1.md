===VERDICT START===
# VERDICT: ontology-coderabbit-r1 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 1

Scope: commit `706ed58` (`git diff ef2a21d..706ed58`) on branch `slice/ontology-update`.
Read-only for source; mutation copies under `/tmp/qp1-check{,2,3}`.

## Verdict summary

Both CodeRabbit findings are fixed with file:line evidence and guarded by tests that
actually run. Two mutation proofs confirm the guards fail on regression. Full suite:
34 passed, 35 skipped. No test deleted or weakened; the diff is confined to
`ontology/join_hints.yaml` (+2 `output_table` lines) and `tests/test_ontology.py`
(+1 `output_table` key, +10/-4 `_canonical_kg_vocabulary` refactor).

## Item 1 — `output_table` on the two `gold_sec_kg` lineage entries

- `ontology/join_hints.yaml:54` `silver_sec_sources_to_gold_sec_kg_nodes.output_table: gold_sec_kg_nodes`
- `ontology/join_hints.yaml:61` `silver_sec_sources_to_gold_sec_kg_edges.output_table: gold_sec_kg_edges`
- Both resolve in `ontology/table_semantics.yaml:208` (`gold_sec_kg_nodes`) and `:214`
  (`gold_sec_kg_edges`).
- `tests/test_ontology.py:76` adds `output_table` to the `_table_references()` key set, so
  `test_every_referenced_table_has_semantics` (line 310) now covers it.

Mutation proof (M1): in a `/tmp` copy, set `output_table: NONEXISTENT_TABLE_XYZ` →
`python3 -m pytest tests/test_ontology.py::test_every_referenced_table_has_semantics -q` →
**FAILED** `AssertionError: Missing table semantics: ['NONEXISTENT_TABLE_XYZ']`.

## Item 2 — `_canonical_kg_vocabulary` baseline + canonical drift

`tests/test_ontology.py:204-237` now always loads `tests/fixtures/sec_kg_enum_snapshot.yaml`
as the fixed baseline and returns it; only when the canonical `sec_kg/model.py` source is
available (local file, else `git show origin/slice/rag-kg:sec_kg/model.py`) does it
separately assert `snapshot == canonical` to detect drift. This satisfies "always uses the
reviewed snapshot as baseline and compares with canonical enums only when available."

Two mutation proofs:

- M2 (phantom node type, canonical unavailable): in a `/tmp` copy with no `sec_kg/model.py`,
  insert a phantom `PhantomNodeType:` into `knowledge_graph.yaml`, run with `GIT_DIR=/nonexistent`
  so `git show` fails →
  `python3 -m pytest tests/test_ontology.py::test_knowledge_graph_vocabulary_matches_canonical_sec_kg_enums -q` →
  **FAILED** `AssertionError: Extra items in the left set: 'PhantomNodeType'`.
- M3 (snapshot drift, canonical available): mutate the snapshot `node_types` (Company →
  PhantomDrift) and run the same test with the canonical `git show` path intact →
  **FAILED** `AssertionError: sec_kg_enum_snapshot.yaml drifted from canonical sec_kg/model.py`.

## Non-blocking notes

- `_canonical_kg_vocabulary` reads the local `sec_kg/model.py` if present before the git
  fallback; in this worktree the file is absent and `git show origin/slice/rag-kg:sec_kg/model.py`
  resolves, so drift detection is active in the normal test path (verified: `git show` returns
  the canonical `NodeType`/`EdgeType` enums matching the snapshot).
- The 35 skips are expected (no local SQL DDL / defining transforms for many tables); all
  pre-existing skips, unchanged by this diff.

## Checks run
- `python3 -m pytest tests/test_ontology.py -q` → **34 passed, 35 skipped** (5.23s)
- `git diff --check ef2a21d 706ed58` → clean
- M1 `...::test_every_referenced_table_has_semantics -q` (output_table → nonexistent) → 1 failed
- M2 `...::test_knowledge_graph_vocabulary_matches_canonical_sec_kg_enums -q` (phantom node, `GIT_DIR=/nonexistent`) → 1 failed
- M3 `...::test_knowledge_graph_vocabulary_matches_canonical_sec_kg_enums -q` (snapshot drift, canonical available) → 1 failed
===VERDICT END===
