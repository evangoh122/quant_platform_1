===VERDICT START===
# VERDICT: rag-kg (re-check, round 3) — DeepSeek (Schema & API Contract Engineer)
**Status:** CHANGES_REQUESTED
**Round:** 3

Round 3 correctly removes the false chunk-level citations for XBRL facts
(chunk=0 is the genuine, correct outcome — verified below) and fixes the exact
rejection stats + fail-on-unknown. But the production read path is still broken:
`SparkGraphStore` reconstructs `Provenance`/`KgEdge` from Spark `TIMESTAMP`
columns as **naive** datetimes, which `ensure_utc` rejects, so the production
`query_sec_facts` path crashes instead of returning results. The round-2
"provenance column" fix only changed the column name/type (`provenance_json` →
`provenance ARRAY<STRUCT>`); it did not address the timezone semantics, and the
fake-Row test masks this by feeding timezone-aware datetimes and never actually
calling a `SparkGraphStore` method.

## Blocking findings

- [api/services/sec_knowledge_graph.py:177,201,223,260-263 + sec_kg/model.py:247,309]
  `SparkGraphStore` reads Spark `TIMESTAMP` columns directly into
  `Provenance(accepted_ts=p["accepted_ts"])` and
  `KgEdge(valid_from=row.valid_from, accepted_ts=row.accepted_ts)`. PySpark
  `TimestampType` returns a **timezone-naive** `datetime.datetime` on
  `.collect()` (the aware `datetime` written by the pipeline loses its `tzinfo`
  in the Spark round-trip). `Provenance.__post_init__`/`KgEdge.__post_init__`
  call `ensure_utc`, which raises `ValueError: Naive datetime … not allowed`.
  → In production, `query_sec_facts(ticker, metric, period, aware_as_of)` with
  no injected `graph` uses `_get_default_graph()` →
  `SparkGraphStore.iter_nodes()`, which raises on the **first** node (and
  `iter_edges()` on the first edge). Every fact query crashes; no results are
  ever returned. Direct repro:
  `Provenance(accession_number="a", source_chunk_id="c", accepted_ts=datetime(2024,1,1))`
  → `ValueError` (naive); the same holds for `KgEdge.valid_from`. The round-3
  fake-Row test (`TestSparkGraphStoreRoundTrip`) feeds `accepted_ts=p.accepted_ts`
  (aware, copied from the Python-side `Provenance`) and only asserts
  `hasattr(row,"provenance")` — it never instantiates `SparkGraphStore` nor calls
  `get_fact`, so the naive-timestamp crash is invisible to CI. Check3 item 2's
  "`get_fact` returns results through `SparkGraphStore`" is therefore false.
  Fix: re-attach UTC when reading (e.g. `p["accepted_ts"].replace(tzinfo=timezone.utc)`
  or convert via epoch) for both `accepted_ts` and `valid_from` in all four
  `SparkGraphStore` methods.

## Non-blocking notes

- **Structural hierarchy edges are never emitted** (pre-existing, data-driven).
  `filing_accessions` is populated only inside the `filing_rows` loop
  [sec_kg/build.py:396,429], and the `FILED` edge is created only there
  [sec_kg/build.py:432]; `HAS_SECTION`/`HAS_CHUNK` require
  `fid in nodes` [sec_kg/build.py:478-480]. The checked-in sample
  `sec_entities.jsonl` has **no** `entity_type="filing"` rows
  (`input_rows_by_entity_type` = company 2,767 / event 1,741 / risk_factor 1,457
  / xbrl_fact 43,722), so `filing_accessions` is empty and **zero** `FILED`,
  `HAS_SECTION`, `HAS_CHUNK` edges are produced (edge-type histogram confirms:
  only `REPORTED_FACT`/`INSTANCE_OF`/`FOR_PERIOD`/`DISCLOSED_RISK`/
  `REPORTED_EVENT`/`SOURCED_FROM`/`SUPERSEDES`). Result: the 456 `Section` and
  10,720 `Chunk` nodes (17.6% of all nodes) are orphaned, and the 16 `Company`
  nodes are not connected to the 2,767 (synthetic) `Filing` nodes. This violates
  BUILD §canonical-model ("Company FILED Filing, Filing HAS_SECTION Section,
  Section HAS_CHUNK Chunk") and now contradicts the ontology (which lists
  `FILED`/`HAS_SECTION`/`HAS_CHUNK` as deterministic edges on
  `silver_sec_sections`). Non-blocking here because it is not introduced by round
  3 and is data-dependent (production `silver_sec_entities` may contain filing
  rows), but the offline build cannot be declared complete until this is
  reconciled.
- **Residual arbitrary-chunk fallback** [sec_kg/build.py:236]. The
  `return sorted(chunks)[0], False, "chunk"` branch survives for every entity
  type that does not pass `entity_value` (`company`/`filing`/`risk_factor`/
  `event`/`segment`/`product`/`customer`) and for an empty-valued fact. For the
  current sample it is unreachable for facts (all 43,722 are filing-level) and
  for non-fact entities (their accessions fall to `filing:` or their own
  `source_chunk_id` resolves), so the round-2 false-citation defect IS fixed for
  facts. But it is a latent footgun: a future company/event row whose accession
  is in the corpus with a null `source_chunk_id` would silently get an arbitrary
  `citation_level="chunk"` with `synthetic_source=False`.
- **Matcher recall ≈ 0 — but chunk=0 is genuinely correct (non-blocking).**
  Verified: of the 5,118 facts whose accession IS in the 128-accession corpus, 35
  have an exact numeric-value match in some chunk, but all 35 are coincidental
  (e.g. `EarningsPerShareDiluted=1.3` matches "$1.3 billion" of debt;
  `EarningsPerShareBasic=14.2` matches "$14.2 million" of expenses; `=5.43`
  matches "working capital was $5.43 billion"). The matcher's period-or-metric
  guard correctly rejects every one → 0 chunk-level (precision 1.0, no false
  citations). It also cannot handle scale (`"$1.3 billion"` vs `1300000000`) and
  requires the XBRL concept name (`EarningsPerShareDiluted`) or ISO period
  (`2025-10-26`) as a literal substring, which narrative prose never contains, so
  recall for genuine chunk citations is ~0. This is the safe, honest outcome:
  filing-level citation with EDGAR `source_url` is correct. Optionally improve
  scale handling + concept-name normalization, but the period/metric guard is the
  binding constraint.
- **Ontology identity keys still differ** (names now match). CHECK item 6:
  `sec_kg/model.py` node/edge **names** now match `ontology/knowledge_graph.yaml`
  exactly (12 node types = 9 deterministic + 3 optional; 13 edge types = 10 + 3;
  `REPORTED_FACT` is Company→XbrlFact, matching). The ontology lane landed this
  in its round 5 (`fix(ontology): round 5 — KG node/edge names equal the
  canonical sec_kg enums`). Remaining semantic differences are in the *identity
  key* fields only: ontology `XbrlFact.key = [accession_number, entity_key,
  entity_unit, period_start, period_end]` vs model.py
  `xbrl_fact_id = (v1, xbrl_fact, cik, accession, metric, period_start,
  period_end, unit, value, source_chunk_id)`; `Filing.key = accession_number` vs
  `(cik, accession)`. model.py is executable-canonical and its value/source-chunk
  inclusion is required for the SUPERSEDES/restatement behaviour; reconcile at
  merge time.

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/rag` → **pass** (379 passed, 19 skipped)
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → **pass** (658 passed, 67 skipped, ~110 s)
- Offline build (`scripts/build_sec_knowledge_graph.py --format jsonl`) → **pass**
  (63,520 nodes / 136,786 edges, 41.95 s; matches Claude's round-3 rebuild exactly)
- Manifest: `input_rows_by_entity_type` exact; `accepted_rows` 49,687; `rejected_rows` 0; `rejection_reasons` {} → **pass**
- `citation_level`: XbrlFact filing 43,722 / chunk **0**; RiskFactor chunk 1,457 (own `source_chunk_id` in corpus); Event filing 1,741 → **pass**
- Edge histogram: `SOURCED_FROM` 1,457 (RiskFactor only, 0 XbrlFact); `SUPERSEDES` 965; **no** `FILED`/`HAS_SECTION`/`HAS_CHUNK` → structural gap (non-blocking #2)
- Rejection stats exact (`BuildStats.rejected` list + `rejection_counts`); `validate_rejection_reasons` + script `sys.exit(1)` on undocumented → **pass**
- Spark reader/writer schema: reader `row.provenance` == writer `provenance ARRAY<STRUCT<…>>` (round-2 `provenance_json` mismatch fixed) → **pass** on name/type; **fail** on timezone (blocking #1)
- Matcher precision/recall (check3 item 1): chunk=0 genuine; precision 1.0, recall ~0 → **pass** (safe), non-blocking #4
- PIT / restatement (3 `as_of` dates) / ID stability (fixed SHA-256 vector, shuffled input) / instant-vs-duration ID non-collision / `query_sec_facts` typed rejection (naive/string/int `as_of`, non-string metric/period, extra kwarg, injection ticker `'; DROP TABLE --`, `extra='forbid'`, `content_type='untrusted_tool_data'`) → **pass** (green in the 379)
- Ontology alignment (names) → **pass**; identity keys → non-blocking #5
- LLM enrichment: default & zero-budget make 0 client calls; no network/Spark in tests → **pass**
- `resources/jobs.yml:32` `sec_knowledge_graph_build`: no `schedule` block, explicit `--catalog`/`--schema` → **pass**
===VERDICT END===
