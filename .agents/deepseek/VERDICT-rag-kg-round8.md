===VERDICT START===
# VERDICT: rag-kg-round8 — DeepSeek (checker)
Status: APPROVED
Round: 8
Range: f6c6ad4..HEAD (commits de0736e, 6ad55f8, 0f10cc4, 91af3e8, 4479d6d)

## Findings

1. (item 1 — DONE) Test (b) now records the validate marker INTO `write_spy.calls`
   and asserts its index precedes the first write/createDataFrame/sql call.
   - tests/rag/test_sec_knowledge_graph.py:2277-2282 — `_tracking_validate` wraps the
     real `validate_and_raise` and calls `write_spy.record("validate", fn="validate_and_raise")`
     into the same call list.
   - tests/rag/test_sec_knowledge_graph.py:2292-2304 — `validate_idx < write_indices[0]`
     over `write_kinds = ("write", "createDataFrame", "sql")`. The dead `pass` loop from
     round 7 is gone.
   - Mutation B (validate moved after writes) FAILS test (b) at :2301 with
     `validate_and_raise (index 4) must come before first write operation (index 0)`.
     This confirms the order assertion is live, not vacuous.

2. (item 2 — DONE) Schema test asserts per-field dataType AND nullable against the
   documented 9-column manifest, and MapType `valueContainsNull` is genuinely compared.
   - tests/rag/test_sec_knowledge_graph.py:2425-2450 — `_dt_repr` serializes
     MapType as `MapType(k,v,valueContainsNull=...)`; expected fields built from
     `MapType(StringType(), IntegerType(), valueContainsNull=False)`, all `nullable=False`.
   - tests/rag/test_sec_knowledge_graph.py:2452-2463 — per-field `name`, `_dt_repr(dataType)`,
     and `nullable` equality asserts.
   - tests/rag/test_sec_knowledge_graph.py:2094-2098 — fake `_MapType` preserves
     `valueContainsNull`.
   - Mutation C (IntegerType→LongType at pipelines/build_sec_knowledge_graph.py:241) FAILS
     the schema test: `Field 4 (accepted_rows) dataType mismatch: LongType != IntegerType`.
   - Mutation D (MapType valueContainsNull False→True) FAILS the schema test:
     `MapType(...,valueContainsNull=True) != MapType(...,valueContainsNull=False)`,
     proving valueContainsNull is actually asserted.

3. (item 3 — DONE) Test (c) now fails under Mutation A (validate replaced by a dict).
   - tests/rag/test_sec_knowledge_graph.py:2316-2322 — `_spy_validate` spies on
     `validate_and_raise`; tests/rag/test_sec_knowledge_graph.py:2378-2381 asserts
     `len(validate_called) >= 1`.
   - Mutation A (validate_and_raise call replaced by a dict at
     pipelines/build_sec_knowledge_graph.py:103) yields **3 FAILED** — (a) no ValueError,
     (b) validate never recorded, (c) validate never called.

4. No test deleted or weakened. `git diff f6c6ad4..HEAD -- tests` shows 0 removed
   `def test_` functions; only `tests/rag/test_sec_knowledge_graph.py` changed
   (+69/-21). The 21 removed lines are the round-7 dead `pass` loop, the old
   `call_order` list, and the old count/name-only asserts — all replaced by stronger
   assertions, not weakened.

## Counts (reproduced independently)

- `python3 -m pytest tests/rag -q` → 392 passed, 19 skipped, 0 failed.
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → 392 passed, 19 skipped, 0 failed.
- `TestPipelineValidation` → 4 passed (a, b, c, schema) in both modes.
- Note: MiMo's self-reported "8 failed psycopg" does NOT reproduce in this environment;
  0 failures on both the plain and hidden-pyspark runs.

## Mutation proofs (fresh `/tmp` copies)

- Mutation A — validate_and_raise replaced by dict → 3 FAILED (a, b, c), 1 passed (schema).
- Mutation B — validate_and_raise moved after table writes → 2 FAILED (a, b), 2 passed (c, schema).
- Mutation C — IntegerType→LongType for `accepted_rows` → 1 FAILED (schema test).
- Mutation D — MapType valueContainsNull False→True → 1 FAILED (schema test).

## Checks run

- `git log --oneline -15` → confirms range f6c6ad4..HEAD on slice/rag-kg (ahead of origin by 11).
- `git diff f6c6ad4..HEAD --stat -- tests` → only test_sec_knowledge_graph.py (+69/-21).
- `git diff f6c6ad4..HEAD -- tests | grep -c '^\-.*def test_'` → 0.
- `python3 -m pytest tests/rag -q` → pass (392).
- pyspark-hidden shim run → pass (392).
- Mutations A/B/C/D in `/tmp/rag-kg-round8-mut-{A,B,C,D}` → each named test FAILS as required.

## Conclusion

All three build-request items are complete with file:line evidence, every requested
mutation proof fails on the mutated copy, no test was deleted or weakened, and the full
suite passes in both plain and hidden-pyspark modes. APPROVED.
===VERDICT END===
