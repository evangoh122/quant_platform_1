# BUILD: SEC knowledge graph round 6, Codex review (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests.

Codex (`.agents/codex/VERDICT-rag-kg.md`), one blocking issue:
1. **The production Delta pipeline ignores rejection validation.**
   `pipelines/build_sec_knowledge_graph.py:~94` gets `stats` from `build_graph()` and goes straight
   to writing; it never calls `validate_rejection_reasons()` (`sec_kg/build.py:~865`).
   - Before ANY table write, call the validator. Any unknown reason → raise, write nothing, exit
     non-zero.
   - Emit the exact stats: input rows by entity_type, accepted, rejected by reason. Log them, and
     write a run manifest (e.g. a small `gold_sec_kg_build_runs` Delta table, or a JSON in a UC
     volume path from config; pick one, document it, and add the schema to `docs/DATA_SCHEMAS.md`).
   - Use ONE shared function for the offline script and the Databricks pipeline, so their behaviour
     can't drift.
   - Test with a fake Spark: an unknown reason → no write calls (spy) and an exception; known
     reasons → the writes happen and the manifest has the exact counts.
2. **(Non-blocking, do it)** Add an exact-value assertion for `neighbors()` edge timestamps. A
   mutation adding 28,800 s to the neighbor edge reads must fail it (prove it in /tmp).

Run `python3 -m pytest -q -p no:cacheprovider tests/rag`, and the full suite with
`--ignore=tests/lakebase`, both with pyspark hidden too. LF line endings only. Don't touch
`.agents/dispatch.sh`. Write `.agents/mimo/VERDICT-rag-kg-round6.md`.
