# BUILD rag-kg round 13 (builder: MiMo) — concept_norm migration

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-kg. Descriptive commits. NEVER delete or weaken tests.
DeepSeek verdict: .agents/deepseek/VERDICT-rag-kg-round12.md finding 2 (finding 1 was fixed by Claude in the latest commit — don't touch it).

Existing gold_sec_kg_nodes tables lack `concept_norm`; CREATE TABLE IF NOT EXISTS won't add it, so the merge fails on schema mismatch and old rows
(NULL concept_norm) silently vanish from concept searches.
1. In pipelines/build_sec_knowledge_graph.py add a forward-only, re-runnable `ensure_concept_norm_column(spark, fqn)` that checks the table schema and
   runs `ALTER TABLE <fqn> ADD COLUMNS (concept_norm STRING)` only if missing (follow the pattern of
   pipelines/run_silver_gold.py ensure_model_availability_columns), called before the MERGE. A full rebuild then populates concept_norm via the
   matched-update path — confirm the MERGE updates concept_norm for matched rows.
2. Query path: until a rebuild has run, rows with NULL concept_norm must not silently disappear — fall back to comparing the normalised
   entity_key/metric parsed with get_json_object(properties_json, '$.entity_key') (structured JSON path, NOT substring) when concept_norm IS NULL,
   OR raise a clear "rebuild required" error if any NULL concept_norm rows exist. Pick one, document it in docs/DEPLOYMENT.md.
3. Tests (fake Spark): table without the column → ALTER issued once; with the column → no ALTER; a NULL-concept_norm row is handled per (2).
   Mutation (copy via `git archive HEAD | tar -x -C /tmp/<dir>`, paste output): skip the ALTER → test FAILS.
Acceptance: python3 -m pytest tests/rag -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-kg-round13.md. Commit everything.
