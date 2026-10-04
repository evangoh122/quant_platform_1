# BUILD ontology — CodeRabbit PR #22 fixes (builder: MiMo)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/ontology-update. Descriptive commits. NEVER delete or weaken tests.
CodeRabbit (2 minor, valid):
1. ontology/join_hints.yaml ~51-62: add an explicit `output_table` field to `silver_sec_sources_to_gold_sec_kg_nodes` (gold_sec_kg_nodes) and
   `silver_sec_sources_to_gold_sec_kg_edges` (gold_sec_kg_edges). Keep their silver input tables and join keys. If tests/test_ontology.py resolves
   table references, make it resolve `output_table` too (it must exist in table_semantics.yaml).
2. tests/test_ontology.py ~203-223 `_canonical_kg_vocabulary()`: always assert the KG vocabulary against the reviewed snapshot
   (tests/fixtures/sec_kg_enum_snapshot.yaml) as the fixed baseline; separately, only when the canonical sec_kg source is importable/available,
   compare the snapshot with the canonical enums. (Today the snapshot is only a fallback.)
Acceptance: python3 -m pytest tests/test_ontology.py -q passes; mutation (in /tmp copy): add a phantom node type to knowledge_graph.yaml → a
snapshot test FAILS even when the canonical source is unavailable. .agents/mimo/VERDICT-ontology-coderabbit-r1.md. Commit everything.
