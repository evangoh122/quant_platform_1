# CHECK: ontology CodeRabbit r1 (checker: DeepSeek) — small

Read-only. Commit 706ed58 (diff ef2a21d..706ed58). CodeRabbit asked for: (1) output_table on the two gold_sec_kg lineage entries;
(2) _canonical_kg_vocabulary always uses the reviewed snapshot as baseline and compares with canonical enums only when available.
Verify both; output_table values resolve in table_semantics.yaml and are covered by the reference-resolution test (mutation: set output_table to a
non-existent table → FAILS); phantom node type in knowledge_graph.yaml → a test FAILS with the canonical source unavailable (simulate by running
in a /tmp copy where sec_kg/model.py is absent and `git show` of the branch fails, e.g. GIT_DIR=/nonexistent). Run python3 -m pytest tests/test_ontology.py -q.
Write .agents/deepseek/VERDICT-ontology-coderabbit-r1.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
