# BUILD rag-kg round 12 (builder: MiMo)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-kg. Commit after each item, descriptive messages.
NEVER delete or weaken existing tests. DeepSeek verdict: .agents/deepseek/VERDICT-rag-kg-round11.md (2 blocking).

1. Concept matching on a STRUCTURED, NORMALISED column (closes escaping false-negatives, NFKC one-sidedness, and predicate injection):
   - At build time add a node column `concept_norm` = NFKC-normalised, lower-cased entity_key (or metric when entity_key absent), computed in Python
     with the SAME normalize_unicode() the JSONL store uses. Add it to the gold_sec_kg_nodes DDL/StructType and docs/DATA_SCHEMAS.md.
   - Spark query: `F.col("concept_norm") == normalize_unicode(concept).lower()` — exact equality on a column; NO substring search on properties_json.
   - JSONL store: compare against the same normalised value (parity).
   - Tests (parity harness run against BOTH stores, the Spark one through a fake that EVALUATES column equality): concept `a"b`, a backslash value,
     full-width `Ｒｅｖｅｎｕｅ` vs `revenue`, injection attempt `revenue","metric":"netincome` (must match NOTHING), `revenue` vs `revenues`
     (no match). Mutation: switch Spark back to the JSON substring → FAILS.
2. As-of-before-LIMIT must be tested against the SPARK path. The fake Spark currently stubs F.exists to a bare `_FakeCol("exists")` (:1582) and
   `_eval` treats unknown conditions as True (:1539-1540), so the predicate is a no-op. Make the fake evaluate `F.exists(array, lambda)` for real
   (apply the lambda to each element) and make `_eval` RAISE on unknown expressions instead of returning True. Then add the Codex probe on the Spark
   store: a future-only row followed by an eligible row, limit=1 → returns the eligible row. Mutation (in /tmp copy, paste output): remove the
   Spark `df.where(F.exists(...))` → FAILS.
Acceptance: python3 -m pytest tests/rag -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-kg-round12.md with counts + mutation outputs. Commit everything.
