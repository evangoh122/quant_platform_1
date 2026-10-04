# CHECK: rag-kg round 11 (checker: DeepSeek)

Read-only. Mutation proofs in /tmp copies (cp -r to /tmp/kg11-mut-*). Write .agents/deepseek/VERDICT-rag-kg-round11.md between ===VERDICT START=== /
===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line, counts, mutation results.
Build request: .agents/requests/BUILD-rag-kg-round11.md (from Codex .agents/codex/VERDICT-rag-kg-review3.md). Commit 3428c29.
1. As-of before LIMIT: Codex's probe — future-only row then eligible row, limit=1 → returns the eligible row. Mutation: as-of after limit → FAILS.
2. Concept matching: Spark uses `F.lower(properties_json).contains('"entity_key":"<lowered>"')` (api/services/sec_knowledge_graph.py:445-452);
   the JSONL store uses `normalize_unicode(node_concept).lower() != concept.lower()` (:186). properties_json is written with
   json.dumps(sort_keys=True, separators=(",",":")) (sec_kg/model.py:339) — check ensure_ascii. Find parity breaks:
   (a) a concept containing a double quote, backslash or non-ASCII char (json escaping `\"`, `\\`, `\uXXXX` vs raw input);
   (b) Unicode normalisation (NFKC) applied on one side only;
   (c) a user-supplied concept containing `","metric":"` or quotes — can it widen the match (predicate injection into the substring)?
   (d) `"entity_key":"revenue"` is a prefix of `"entity_key":"revenues"`? (the closing quote makes it exact — verify).
   Any real parity break or widening is a finding; recommend a structured-column comparison (get_json_object / from_json) instead.
3. Driver cap: max_entities raises a clear error before OOM; documented; no remaining "no driver-wide collect" claims.
4. Functional fake-Delta stale-delete test; mutation: remove the actual whenNotMatchedBySourceDelete() calls (leave comments) → FAILS.
No tests deleted/weakened except the source-grep test replaced in item 4 (git diff 4ff9d46..HEAD -- tests).
Run: python3 -m pytest tests/rag -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps.
