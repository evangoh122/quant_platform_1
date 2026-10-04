===VERDICT START===
Reviewer: Claude Sonnet subagent (stopgap for Codex, usage-limited)
Status: CHANGES_REQUESTED

Tests: python3 -m pytest tests/rag -q -> 457 passed, 19 skipped (skips unrelated: optional deps/removed modules).

Prior Codex findings: LIMIT-before-as-of fixed (F.exists pushed before .limit, find_nodes ~L469-482); concept_norm equality in place; driver cap present; delete test functional. Migration wired before CREATE/MERGE (pipelines/build_sec_knowledge_graph.py:249). valid_from==accepted_ts UTC enforced (sec_kg/model.py:312, build.py:364). Citations use Decimal. Tool: ticker allow-listed, metric<=128, period<=32, tz-aware as_of, extra=forbid.

Findings
P1 api/services/sec_knowledge_graph.py:~416-427 (find_nodes): the DataFrame is built with .select("node_id","node_type","label","properties_json","build_version", transform(provenance)) which DROPS concept_norm, then F.col("concept_norm") is used for the NULL guard and equality filter. On real Spark this is an UNRESOLVED_COLUMN AnalysisException for every concept search. Hidden because every mock DataFrame defines select() as `return self` (tests ~1495, 2054, 2858). Fix: add "concept_norm" to the select; add a test with a select that actually projects columns. (Could not run real Spark locally: only Databricks Connect present; to be live-checked by Claude from WSL.)
P2 pipelines/build_sec_knowledge_graph.py:150-156: max_entities cap is checked AFTER all rows are collected into driver lists, so it cannot prevent OOM (docstring says "before OOM"). Check a count() on the source DataFrames before collecting.
P2 find_nodes NULL-concept guard: concept_norm is None for nodes with empty concept (model: `if raw_concept else None`); a legit NULL on the filtered node_type would raise "full rebuild required". Restrict guard to legacy rows (e.g. node_type has concept AND properties_json contains a concept key).
P3 query_sec_facts: metric/period only length-bounded, not allow-listed.

Mutations (copies in /tmp/rv4_*), all killed:
1. Disable as-of pre-limit filter -> test_spark_limit_1_returns_eligible fails.
2. concept via properties_json substring -> 12 failures.
3. Remove ensure_concept_norm_column call -> test_build_issues_alter_before_merge fails.
4. Disable max_entities check -> test_cap_raises_on_overflow fails.
Counts: P0 0, P1 1, P2 2, P3 1.
===VERDICT END===
