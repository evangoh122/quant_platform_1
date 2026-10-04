===VERDICT START===
Reviewer: Claude Sonnet subagent (stopgap for Codex, usage-limited)
Status: APPROVED

Baseline: python3 -m pytest tests/rag -q -> 478 passed, 19 skipped (HEAD 4d23e80).

Mutations (git archive copies in /tmp, tests/rag each):
- P1 remove "concept_norm" from find_nodes select (api/services/sec_knowledge_graph.py:424): 16 failed (concept-search and guard tests). Killed; fake select now projects.
- P2 max_entities check moved after collect (pipelines/build_sec_knowledge_graph.py:~102-111): TestDriverMemoryCap::test_mutation_count_after_collect_fails fails. Killed.
- P2 legacy guard without node_type isin("XbrlFact","Metric") (sec_knowledge_graph.py:~453): Company/Filing no-guard tests fail. Killed. Guard (lines 453-467) requires concept-bearing type, NULL concept_norm, and non-empty entity_key or metric.
- P3 fullmatch -> match (agent/tools_retrieval.py:275,300): trailing-newline test ("Revenues\n"/"2024-01-28") and slash-period test fail. Killed.

Round-15 diff scan: nothing wrong found. Minor, non-blocking: guard treats a missing JSON key (SQL NULL) as "not non-empty", which is the intended lenient behaviour.
===VERDICT END===
