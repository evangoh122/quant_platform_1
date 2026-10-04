# REVIEW: SEC knowledge graph lane (reviewer: Codex gpt-5.6-sol)

Independent REVIEWER after DeepSeek approved round 8 (.agents/deepseek/VERDICT-rag-kg-round8.md). Do NOT edit repo files; mutation
proofs in /tmp copies (cp -r to /tmp/kg-review-*). Print verdict between ===VERDICT START=== and ===VERDICT END===, "Status: APPROVED"
or "Status: CHANGES_REQUESTED", numbered findings with file:line, test counts, mutation results.

Scope: branch slice/rag-kg vs origin/main (sec_kg/, pipelines/build_sec_knowledge_graph.py, scripts/build_sec_knowledge_graph.py,
api/services/sec_knowledge_graph.py incl. query_sec_facts, tests/rag/test_sec_knowledge_graph.py, docs). Original spec:
.agents/requests/BUILD-rag-kg.md. Earlier Codex review that requested changes: .agents/codex/VERDICT-*kg* (check it's resolved).
Review for:
1. Point-in-time: every node/edge carries valid_from = accepted_ts; restatement supersession; query_sec_facts never returns facts
   accepted after the as-of; timestamps are UTC (a past bug was naive datetimes in client local tz, UTC+8).
2. Citations: every fact traces to a filing-level citation; no fabricated chunk ids.
3. Rejection accounting: validate_and_raise before any write; manifest counts exact; explicit schema.
4. Agent-facing tool safety: inputs bounded, no injection into Spark SQL, output size capped.
5. Tests meaningful — run 3 mutations of your own choosing.
Run: python3 -m pytest tests/rag -q
