===VERDICT START===
# VERDICT: rag-kg-round15 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 15
**Range:** 818df88 (fix(kg): round 15) on slice/rag-kg

## Blocking findings

- [tests/rag/test_sec_knowledge_graph.py:3724-3768] `test_mutation_count_after_collect_fails`
  is vacuous — the "spy" it asserts against never records `toLocalIterator`/`collect`.
  `_FakeDataFrame.collect()` (line 2134), `.toLocalIterator()` (line 2136) and `.count()`
  (line 2140) in `_setup_pyspark_mocks` return rows directly and do NOT call
  `write_spy.record(...)`. The assertion `len(iter_calls) == 0` over
  `write_spy.calls[kind in ("toLocalIterator","collect")]` is therefore trivially true
  for every build. **Mutation proof**: moving the cap check back AFTER the
  `toLocalIterator`/`collect` loops (exact old-code reversion) still yields
  `475 passed, 19 skipped` — the mutation is NOT killed. The acceptance criterion
  "Mutation: check after collect → FAILS" is unmet; the test does not prove the
  count happens before collecting. (The production fix itself
  pipelines/build_sec_knowledge_graph.py:102-111 is correct; only the guard test is dead.)

- [agent/tools_retrieval.py:275] metric regex `^[A-Za-z][A-Za-z0-9._:\-]*$` and
  [agent/tools_retrieval.py:294-299] period regex (`^\d{4}$` etc.) are anchored with
  `$` under `re.match`, not `\Z`/`fullmatch`. `$` matches *before* a trailing newline,
  so `"Revenues\n"` (metric) and `"2023\n"` (period) PASS validation instead of being
  rejected. **Empirical proof** (in-repo, `PYTHONPATH` set):
  `query_sec_facts("ZZZZZZ", "Revenues\n", "2024-01-28", as_of)` → only the ticker
  allow-list error (1 validation error); no "XBRL concept name" error. Same for
  `"2023\n"` (1 error). Contrast `"Revenues;DROP"` / `"2023/2024"` → 2 errors.
  The CHECK explicitly requires `"Revenues\n"` be rejected — it is not.

## Non-blocking notes

- Point 1 (P1) is CORRECT and guarded. `concept_norm` is in the `find_nodes`
  `.select()` (api/services/sec_knowledge_graph.py:424); I audited every other
  `.select()` in the file (iter_nodes 252, iter_edges 290, get_node 323,
  get_edges_for_node 366, find_nodes 422, get_edges 543) — every `F.col()` used
  after a `.select` is projected. The fake `select()` now really projects and
  raises `AttributeError` on a non-projected column. **Mutation proof**: removing
  `"concept_norm"` from the select → 11 concept/NULL-guard tests FAIL
  (`UNRESOLVED_COLUMN: 'concept_norm' not in projected row`). Killed.
- Point 3 (legacy guard) is correct. Guard restricted to `node_type ∈ {XbrlFact,
  Metric}` with non-empty `$.entity_key`/`$.metric` and NULL `concept_norm`
  (api/services/sec_knowledge_graph.py:453-465). Tests cover both sides:
  Company/Filing pass; XbrlFact/Metric with non-empty entity_key raise; empty
  entity_key passes.
- [tests/rag/test_sec_knowledge_graph.py:4947] `test_metric_null_concept_norm_guard_fires`
  uses a synthetic Metric node whose properties carry `entity_key`, but the real
  build (sec_kg/build.py:601-602) stores Metric concepts under `"concept"`, not
  `entity_key`/`metric`. On real Spark such a Metric node would have
  `get_json_object($.entity_key)=NULL` and `NULL.isin(...)=NULL`, so the guard
  would not actually fire for real Metric rows. The test passes on the fake only
  because the fake's `json_isin` treats an absent key as `""`. Not a live defect
  (Metric nodes legitimately have NULL concept_norm and the guard *not* firing is
  the desired outcome), but the test's data does not reflect the real schema and
  its name/docstring overstate what it verifies.
- Metric nodes are built with `concept_norm = NULL` unconditionally
  (build computes `props.get("entity_key", props.get("metric",""))` which is empty
  for `{"concept": ...}`). Pre-existing from round 12, out of scope for this round.

## Checks run

- `python3 -m pytest tests/rag -q` → **475 passed, 19 skipped, 1 warning** (27.2s)
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **475 passed, 19 skipped**
- Mutation 1 (remove `"concept_norm"` from find_nodes select, archive copy) →
  `pytest tests/rag/test_sec_knowledge_graph.py -k 'Concept or concept'` → **11 failed**
  (`UNRESOLVED_COLUMN: 'concept_norm' not in projected row`). Killed.
- Mutation 2 (move max_entities check back after collect, archive copy) →
  `pytest tests/rag -q` → **475 passed** (NOT killed — see blocking finding #1).
- Metric/period trailing-newline probe (in-repo) → `"Revenues\n"` / `"2023\n"`
  accepted (only ticker error); `"Revenues;DROP"` / `"2023/2024"` rejected.
- `re.match(r"^[A-Za-z][A-Za-z0-9._:\-]*$", "Revenues\n")` → True (matches);
  with `\Z` or `fullmatch` → False.
===VERDICT END===
