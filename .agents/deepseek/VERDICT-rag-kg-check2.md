===VERDICT START===
# VERDICT: rag-kg (re-check, round 2) — DeepSeek (Schema & API Contract Engineer)
**Status:** CHANGES_REQUESTED
**Round:** 2

Round 2 correctly fixed the instant-period defect (43,722 XbrlFact nodes now
emitted: 32,143 duration + 11,579 instant). But the **key question is answered
"yes, and it is wrong"**: the 5,118 `citation_level=chunk` facts are produced by
an accession→"lexicographically-smallest-chunk" fallback, not because the fact's
own `source_chunk_id` resolved. I sampled 20 chunk-level facts and **0/20 chunk
texts contain the fact's value** and only **1/20** contains the metric's line
item. The round-1 provenance defect is therefore only half-fixed: citations now
point at *some* corpus chunk, but that chunk does not actually contain the fact.
Per the re-check instruction these must be filing-level. Two further defects
(the manifest rejection count and a broken Spark read path) also remain.

## Blocking findings

- [sec_kg/build.py:128-132] Chunk-level citations are false. `resolve_source_chunk_id`
  falls back to `sorted(corpus_by_accession[acc])[0]` (an arbitrary chunk of the
  same filing) and labels it `citation_level="chunk"`, `synthetic_source=False`.
  In the supplied data **0 of 43,722** `xbrl_fact` `source_chunk_id` values appear
  in `sec_corpus.jsonl` (distinct `source_chunk_id`s = 43,722, corpus `chunk_id`s
  = 10,720, intersection = 0). The direct-resolution branch therefore never fires;
  every one of the 5,118 chunk-level facts comes from this accession fallback.
  → A chunk-level citation is asserted without the chunk containing the fact.
  Sampled 20 chunk-level facts: value present in 0/20, metric line-item present
  in 1/20 (e.g. `NetIncomeLoss=414600000` → chunk text about "sales channel";
  `EarningsPerShareBasic=1.87` → chunk text about "allowance for credit losses").
  The re-check requirement ("a chunk-level citation must mean the chunk actually
  CONTAINS the fact") is violated; these must be downgraded to `filing` level
  (with `source_url`), or the fallback must verify the value/metric appears.

- [api/services/sec_knowledge_graph.py:173,220] `SparkGraphStore` reads a
  non-existent column. `iter_nodes`/`get_node` do `json.loads(row.provenance_json)
  if hasattr(row,'provenance_json') else []`, but the Delta table created by
  `pipelines/build_sec_knowledge_graph.py:107` stores the column `provenance` as
  `ARRAY<STRUCT<...>>` (not a JSON string named `provenance_json`).
  `hasattr(row,'provenance_json')` is always `False`, so `provenance` is always
  `()`. → In the production path (`query_sec_facts` with no injected `graph`
  uses `_get_default_graph()` → `SparkGraphStore`, tools_retrieval.py:288-293),
  every node has empty provenance, so `get_fact`'s PIT predicate
  `[p for p in node.provenance if p.accepted_ts <= as_of]` is always empty and
  **all queries return no results / empty provenance**. The Delta reader and the
  Delta writer disagree on both column name and type. No test covers this
  (pyspark is hidden in CI).

- [scripts/build_sec_knowledge_graph.py:135,189] Rejection reporting still broken
  (carried over from round 1, unchanged). `rejected_row_count = len(entities) -
  len(nodes)` = **-13,820** for the real build (49,687 entities, 63,507 nodes),
  a negative number because nodes are unique/aggregated, not per-row. `rejection_reasons`
  is hard-coded `{}`. `build_graph` tracks `BuildStats.rejection_counts` but never
  returns it, so the spec's "rejected-row counts/reasons" and the re-check's "exact
  counts and a FAIL on undocumented rejects" are not met. There is no FAIL on
  undocumented rejects.

## Non-blocking notes

- [sec_kg/build.py:414] Version sort key is still `(accepted_ts, accession)`;
  BUILD spec §canonical-model requires `(accepted_ts, accession_number, node_id)`.
  Ties within one accession+accepted_ts depend on stable sort/input order (a
  determinism edge case). Unchanged from round 1.
- [scripts/build_sec_knowledge_graph.py:75-77,193] `--as-of` is parsed and written
  to the manifest but never applied (build is full-history; a no-op flag is
  misleading). Unchanged from round 1.
- Ontology alignment (CHECK item 6): `sec_kg/model.py` still does **not** match
  `ontology/knowledge_graph.yaml` on `slice/ontology-update`. model.py is
  faithful to BUILD-rag-kg.md (which the spec declares canonical), but the two
  vocabularies diverge. Full mismatch list unchanged from round 1 (verbatim): edge
  names differ (`FILED` vs `COMPANY_FILED_FILING`, etc.), `REPORTED_FACT` is
  Company→Fact vs ontology's `FILING_REPORTS_FACT` Filing→Fact, ontology-only
  `CHUNK_MENTIONS_COMPANY`/`SEGMENT_REPORTS_FACT`/`PRODUCT_REPORTS_FACT`/
  `CUSTOMER_RELATED_TO_EVENT`, model.py-only `SOURCED_FROM`/`SUPERSEDES`, and
  differing identity keys (XbrlFact, Filing, RiskFactor/Event). Reconcilable at
  merge; model.py is executable-canonical.
- [pipelines/build_sec_knowledge_graph.py:50-67] `sections_df.select(...).collect()`
  and `entities_df.collect()` pull the entire source + graph to the driver,
  violating "do not collect the graph to the driver" (BUILD §sizing). Local
  20 MB inputs are fine; 557-ticker production Delta is not. MiMo/perf lane
  concern, non-gating here.
- [api/services/graph_rag_engine.py] Legacy `graph_triples` DuckDB path is intact
  with no deprecation note (BUILD item 7's fallback requires one). `query_sec_facts`
  is correctly separate and authoritative, so no non-PIT fact mixing — cosmetic.
- [resources/jobs.yml] `sec_knowledge_graph_build` is unscheduled and passes
  `--catalog`/`--schema` explicitly — correct. `docs/DEPLOYMENT.md:262-266`
  recommends `ZORDER BY (node_type)`/`(edge_type, valid_from)` while the pipeline
  partitions by those very columns (minor doc inconsistency).

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/rag` → **pass** (370 passed, 19 skipped)
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → **pass** (649 passed, 67 skipped, 174 s)
- Offline build (`scripts/build_sec_knowledge_graph.py` via `build_graph`) → **63,507 nodes / 141,904 edges** (matches MiMo round-2 rebuild exactly). XbrlFact 43,722 (duration 32,143 + instant 11,579); `citation_level` chunk 5,118 / filing 38,604; SOURCED_FROM 6,575; SUPERSEDES 965. Build ~15 s (<30 s target).
- ID uniqueness: 63,507 unique node_ids, 141,904 unique edge_ids → **pass**. Instant-vs-duration ID collision test (`test_instant_and_duration_same_metric_no_collision`) → **pass**; `xbrl_fact_id` includes `period_start` (empty for instant) so the two never collide.
- Provenance resolvability: 0/43,722 fact `source_chunk_id`s in corpus → **fail** (blocking #1). Field completeness (nonblank accession/chunk/UTC, `valid_from==accepted_ts`) → **pass**.
- Chunk-contains-fact sample (20 chunk-level facts) → **fail**: 0/20 contain value, 1/20 contain metric line item.
- XBRL normalization spot-check (10 real facts) → **pass**: units (USD, USD/shares, shares, AFN), instant vs duration, sign (`-0.29` EPS), scale (integer vs decimal) all preserved; `parse_decimal` returns correct signed `Decimal`.
- Restatement at 3 `as_of` (synthetic v1/v2/v3) → **pass**: before-all empty; mid returns v2 (is_restatement=True, supersedes set); after-all returns v3; all 3 retained; 2 SUPERSEDES edges; no future provenance leaks.
- `query_sec_facts` typed rejection (naive/string/int `as_of`, non-string metric/period, extra kwarg, injection ticker `'; DROP TABLE --`) → **pass** (pydantic `extra='forbid'`). Returns `content_type='untrusted_tool_data'` and `citation_level` + `source_url` in each result → **pass**.
- LLM enrichment: default & zero-budget call the fake client 0 times; no network/Spark in tests → **pass**.
- `resources/jobs.yml:32` unscheduled, explicit catalog/schema → **pass**.
===VERDICT END===
