===VERDICT START===
# VERDICT: rag-kg-round11 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 11
**Range:** 4ff9d46..3428c29 (HEAD 6bf56df, branch slice/rag-kg, tree clean)

## Blocking findings

1. [api/services/sec_knowledge_graph.py:464-474] Item 1 (P1) Spark-side as-of-before-LIMIT
   predicate has **no functional regression test** — the required mutation proof ("move
   as-of back after limit → FAILS") does not hold. Removing the entire `df.where(F.exists(...))`
   block (i.e. as-of applied only post-collect, after the limit budget was already consumed)
   leaves **all 439 tests green** (mutation run in /tmp/kg11-mut-asof → `439 passed, 19 skipped`).
   Root cause, two layers:
   - `TestLimitBeforeAsOf` (tests/rag/test_sec_knowledge_graph.py:3382-3450) exercises only
     `JsonlGraphStore` (load_from_build at :3417-3420), whose Python loop applies the as-of
     filter *before* the `len(results) >= limit` break (api/services/sec_knowledge_graph.py:192-199),
     so it cannot observe Spark-side ordering.
   - The fake Spark stubs `F.exists` to a bare `_FakeCol("exists")`
     (tests/rag/test_sec_knowledge_graph.py:1582), and `_eval` treats any non-expression
     condition as `True` (:1539-1540), so the predicate is a no-op in every Spark test.
   Net: the P1 fix is untested against the actual Spark predicate; the Codex adversarial
   probe (future-only row + eligible row, limit=1 → eligible) is not reproduced in code.

2. [api/services/sec_knowledge_graph.py:447-454] Item 2 (P1) still matches on a **JSON
   substring**, not a structured field, despite the build request requiring "a structured
   field, not a JSON substring". Three concrete parity breaks vs `JsonlGraphStore` confirmed
   by script (parity harness below):
   - (a) **Escaped chars → Spark false-negative.** A concept containing `"` or `\` matches in
     JSONL (exact value compare) but not Spark: `deterministic_json` (sec_kg/model.py:337-340)
     writes `\"`/`\\`, so `F.lower(properties_json).contains('"entity_key":"a"b"')` never matches.
     `concept='a"b'` → jsonl=True, spark=False.
   - (b) **NFKC one-sided → Spark false-negative.** `JsonlGraphStore` applies
     `normalize_unicode` (NFKC, sec_kg/model.py:58-65) to the stored value before `.lower()`;
     Spark's `F.lower` does no NFKC. Full-width stored value `Ｒｅｖｅｎｕｅ` → jsonl=True, spark=False.
   - (c) **Predicate injection / widening → Spark false-positive.** `deterministic_json`
     sorts keys, so concept `revenue","metric":"netincome` constructs the literal substring
     `"entity_key":"revenue","metric":"netincome"`, which matches a node whose
     `entity_key="revenue"` AND `metric="netincome"` in Spark but returns nothing in JSONL
     (`jsonl=False, spark=True`). A user-supplied concept can widen the match.
   - (d) Verified non-issue: `"entity_key":"revenue"` does NOT match `"entity_key":"revenues"`
     (the closing quote keeps it exact) — jsonl=False, spark=False.
   Recommend `get_json_object`/`from_json` structured-column comparison on `entity_key`/`metric`
   with `F.lower()`, which closes (a), (b), and (c).

## Non-blocking notes

3. [pipelines/build_sec_knowledge_graph.py:124-131] Item 3 (P2) driver cap is implemented and
   covered: `MemoryError` raised when `len(chunk_metadata)+len(entities) > max_entities` before
   the merge; module docstring documents the driver-bound design; the misleading
   "avoid driver-wide collect" comments were corrected. `TestDriverMemoryCap` (3 tests) pass.

4. [api/services/sec_knowledge_graph.py:264,298] Pre-existing (out of this round's build scope):
   `iter_nodes()`/`iter_edges()` still carry the misleading comment "Use toLocalIterator to avoid
   driver-wide collect of whole table" — `toLocalIterator` streams but the `nodes`/`edges` lists
   still accumulate fully in driver memory with no limit/cap.

## Item 4 (P2) — mutation proof PASSES

- Mutation (in /tmp/kg11-mut-del): removed both `.whenNotMatchedBySourceDelete()` calls
  (pipelines/build_sec_knowledge_graph.py:270,277), leaving comments/error text intact →
  `TestFunctionalStaleDelete::test_merge_calls_when_not_matched_by_source_delete` FAILS
  (0 delete calls ≠ 2) and `test_stale_row_removed_on_second_build` FAILS (`7 < 7`). **2 failed**.
  The functional fake-Delta test genuinely detects removal of the delete behaviour.

## Checks run

- `python3 -m pytest tests/rag -q` → **439 passed, 19 skipped, 1 warning**
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **439 passed, 19 skipped**
- `python3 -m pytest tests/rag/test_sec_knowledge_graph.py -q -k 'DriverMemoryCap'` → **3 passed**
- Mutation /tmp/kg11-mut-asof (remove Spark as-of `where`) → **439 passed** (proof FAILS: no test catches it)
- Mutation /tmp/kg11-mut-del (remove `whenNotMatchedBySourceDelete`) → **2 failed** (proof holds)
- Concept parity script (/tmp/kg11_concept_parity.py) → 3 PARITY-BREAKs (a/b/c) + 1 non-issue (d)
===VERDICT END===
