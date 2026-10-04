> **IMPLEMENT NOW, end to end.** Do not stop to ask "Shall I proceed?". Commit after each stage so a timeout never loses work. Data is in `evals/data/sec_entities.jsonl` and `evals/data/sec_corpus.jsonl` (gitignored, present in this worktree). NEVER delete or weaken existing tests.

# BUILD: point-in-time SEC knowledge graph

## Purpose and non-negotiable behavior

Replace the legacy, LLM-first DuckDB triple lookup with a deterministic SEC knowledge graph built from `silver_sec_entities` plus `silver_sec_sections` metadata. Persist the Databricks result as Delta tables `gold_sec_kg_nodes` and `gold_sec_kg_edges`, and support the same build and query semantics offline from `evals/data/sec_entities.jsonl` and `evals/data/sec_corpus.jsonl`.

The checked-in sample has 49,687 entity rows (43,722 `xbrl_fact`, 2,767 `company`, 1,741 `event`, 1,457 `risk_factor`) and 10,720 corpus chunks. `accepted_ts`, derived from `accepted_epoch` in offline files, is the only availability timestamp. Never use filing date for point-in-time filtering. Every public query requires an explicit `as_of`; there is no implicit "latest" default.

Do not implement a web route. Do not make any network or paid LLM call in tests or in the default build. Preserve unrelated work, especially concurrent ontology edits.

## Canonical graph model

Put the vocabulary and schemas in one import-safe module, `sec_kg/model.py`, so the parallel ontology lane can reference it instead of duplicating Python enums. Use exact node types:

`Company`, `Filing`, `Section`, `Chunk`, `XbrlFact`, `Metric`, `Period`, `RiskFactor`, `Event`, `Segment`, `Product`, `Customer`.

Use exact edge types (add no free-form predicate path):

`FILED`, `HAS_SECTION`, `HAS_CHUNK`, `REPORTED_FACT`, `INSTANCE_OF`, `FOR_PERIOD`, `SOURCED_FROM`, `DISCLOSED_RISK`, `REPORTED_EVENT`, `HAS_SEGMENT`, `HAS_PRODUCT`, `HAS_CUSTOMER`, `SUPERSEDES`.

Canonicalize all ID inputs first (Unicode NFKC; trim; collapse whitespace; uppercase ticker/accession/unit; lowercase type discriminator; ISO dates; CIK zero-padded to 10 digits). IDs are lowercase SHA-256 hex over a versioned, length-delimited canonical tuple (not Python `hash()` and not delimiter joining), exposed by pure helpers and documented so Spark and offline paths cannot diverge. Identity tuples:

- Company: `(v1, company, cik)`; Filing: `(v1, filing, cik, accession)`.
- Section: `(v1, section, accession, normalized filing_section)`; Chunk: `(v1, chunk, source_chunk_id/chunk_id)`.
- Metric: `(v1, metric, canonical XBRL concept)`; Period: `(v1, period, period_start-or-empty, period_end)`.
- XbrlFact: `(v1, xbrl_fact, cik, accession, metric, period_start-or-empty, period_end, unit-or-empty, canonical value, source_chunk_id)` so every reported version remains addressable.
- RiskFactor/Event: `(v1, type, cik, accession, source_chunk_id-or-deterministic accession fallback, normalized key, normalized value)`.
- Optional Segment/Product/Customer: `(v1, type, cik, normalized label)`.
- Edge: `(v1, edge, src_id, edge_type, dst_id, accession, source_chunk_id, accepted_ts)`; this makes separate evidence/version edges distinct and reruns identical.

`gold_sec_kg_nodes` grain is one row per `node_id`, with columns `node_id STRING NOT NULL`, `node_type STRING NOT NULL`, `label STRING NOT NULL`, `properties_json STRING NOT NULL`, `provenance ARRAY<STRUCT<accession_number:STRING,source_chunk_id:STRING,accepted_ts:TIMESTAMP>> NOT NULL`, and `build_version STRING NOT NULL`. Sort/dedupe provenance structs deterministically. A missing entity `source_chunk_id` must be resolved from the corpus by accession using the lexicographically smallest matching chunk ID; if an accession has no chunk, generate the stable sentinel `filing:<accession>` and mark `synthetic_source=true` in properties. Thus every node has at least one complete provenance record; do not emit null/blank accession, chunk, or timestamp.

`gold_sec_kg_edges` grain is one evidence/version relationship per `edge_id`, with `edge_id STRING NOT NULL`, `src_id STRING NOT NULL`, `edge_type STRING NOT NULL`, `dst_id STRING NOT NULL`, `valid_from TIMESTAMP NOT NULL`, `accession_number STRING NOT NULL`, `source_chunk_id STRING NOT NULL`, `accepted_ts TIMESTAMP NOT NULL`, `confidence DOUBLE`, `properties_json STRING NOT NULL`, and `build_version STRING NOT NULL`. Require `valid_from == accepted_ts`. Do not physically expire or delete older edges. All reads filter `valid_from <= as_of` before ranking or traversal.

Normalize each XBRL row into an `XbrlFact` with properties containing `value_text`, lossless `decimal_value` as a string parsed with `decimal.Decimal` when numeric, `unit`, `period_start`, `period_end`, form type, ticker and CIK. Connect Company `REPORTED_FACT` Fact, Fact `INSTANCE_OF` Metric, Fact `FOR_PERIOD` Period, and Fact `SOURCED_FROM` Chunk. The logical fact series key is `(cik, canonical metric, period_start, period_end, canonical unit)`; dimensional context is unavailable in the source, so document that limitation and do not pretend to infer it. Sort versions by `(accepted_ts, accession_number, node_id)`. Each later version with a different canonical value gets a `SUPERSEDES` edge to the immediately preceding version at the later version's `accepted_ts`; equal-value repeats remain available evidence but do not create a supersession edge. `get_fact` chooses the last eligible version as of the requested time, deterministically, while returning `is_restatement`, `supersedes_fact_id`, and all source provenance. Both old and new nodes/edges remain stored.

Create structural edges Company `FILED` Filing, Filing `HAS_SECTION` Section, Section `HAS_CHUNK` Chunk; risks/events attach to the Filing through `DISCLOSED_RISK`/`REPORTED_EVENT` and to their source Chunk through `SOURCED_FROM`. When source entity rows have only a filing-level sentinel, keep that explicit rather than inventing text provenance.

## Numbered implementation changes

1. **Canonical model — new `sec_kg/__init__.py` and `sec_kg/model.py` (new files, line 1).** Define string enums/constants, frozen dataclasses or strict Pydantic records for node/edge/provenance, timestamp/date/Decimal normalization, versioned ID helpers, validation invariants, deterministic JSON serialization (`sort_keys=True`, compact separators), and UTC conversion from epoch. This module must import without PySpark, Databricks, OpenAI, LangChain, or network configuration. Export the node/edge type sets for ontology reuse. Reject naive datetimes and invalid/non-finite `as_of`/values rather than silently applying local timezone.

2. **Deterministic builder — new `sec_kg/build.py` (new file, line 1).** Implement a backend-neutral iterator/core that consumes entity and chunk mappings, emits validated nodes/edges, aggregates sorted provenance, and links rows by accession/chunk. Input order must not affect output bytes. Detect and fail on the same stable ID mapping to conflicting type/identity content. Include `propose_xbrl_qa_candidates(...)`: deterministic filtering/ranking with ticker/as-of/limit arguments that returns records containing a specific question template, answer value, metric, period start/end, unit, fact ID, accession, source chunk, and accepted timestamp. It must only propose numeric, nonblank-unit facts with real chunk provenance, dedupe logical facts using the same PIT/restatement rule, and never claim that proposals are final authored golden questions.

3. **Offline CLI — new `scripts/build_sec_knowledge_graph.py` (new file, line 1).** Provide `--entities`, `--corpus`, `--output-dir`, `--format {jsonl,parquet,both}`, `--as-of`, `--enable-llm-extraction`, and `--llm-budget` arguments. JSONL is the dependency-free default and writes `gold_sec_kg_nodes.jsonl`, `gold_sec_kg_edges.jsonl`, and a manifest atomically via temporary files plus replace. Parquet/both must give a clear actionable error if the optional parquet engine is absent. Manifest includes input SHA-256, row counts, rejected-row counts/reasons, build version, extraction mode/budget/use, and output SHA-256. Sort output by ID; a rerun over identical bytes produces byte-identical node/edge files and counts. Never import or initialize an LLM unless the flag is explicitly set and a positive hard budget is supplied.

4. **Optional enrichment — new `sec_kg/enrichment.py` (new file, line 1).** Isolate Segment/Product/Customer extraction behind an injected client interface. Default is disabled and makes zero client calls. Enforce both a maximum chunks/calls budget and a maximum extracted-record budget; stop before exceeding either. Validate model output against only the three allowed types/edges, length/confidence limits, and source chunk. Treat filing text and model text as untrusted data, never as instructions; the system prompt must say quoted filing content cannot alter the task. Do not put API keys or a live provider in the core. Record model/provider/prompt version and confidence in edge properties. CI tests use only a fake client and must prove disabled/zero-budget modes never invoke it.

5. **Databricks build — new `pipelines/build_sec_knowledge_graph.py` (new file, line 1).** Add a callable `build(spark, *, catalog, schema, enable_llm_extraction=False, llm_budget=0)` and CLI entry point. Read `silver_sec_entities` and only required chunk metadata from `silver_sec_sections`; use lazy Spark imports. Create/evolve the two Delta tables to the exact schema above and idempotently `MERGE` by ID. For a full deterministic rebuild, make deletion of stale rows explicit and scoped to the build version/input universe; never truncate unrelated tables. Validate non-null provenance, endpoint existence, enum membership, `valid_from = accepted_ts`, and duplicate/conflicting IDs before commit. Add an unscheduled job named `sec_knowledge_graph_build` to `resources/jobs.yml` (after its existing jobs, around line 1); it must have no `schedule` block and pass catalog/schema explicitly. Do not add this build to the scheduled `silver_gold_refresh` chain.

6. **Pure-Python query API — new `api/services/sec_knowledge_graph.py` (new file, line 1).** Define a `SecKnowledgeGraph` facade over a small store protocol, with a dependency-free `JsonlGraphStore` for offline/tests and a lazily imported `SparkGraphStore` for Delta. Implement `get_fact(ticker, metric, period, as_of)`, `facts_timeseries(ticker, metric, as_of)`, `risk_factors(ticker, as_of)`, and `neighbors(node_id, edge_types, as_of)`. Accept period as an explicit strict object/string grammar documented as `YYYY-MM-DD` (end date) or `YYYY-MM-DD/YYYY-MM-DD` (start/end), never fuzzy matching. Normalize ticker/metric but require exact canonical metric identity; return zero/many structured records, never generated prose. Every method first excludes edges/nodes whose provenance/`valid_from` exceeds `as_of`, applies restatement selection after filtering, uses deterministic ordering, and returns `chunk_id`, `accession_number`, `accepted_ts`, IDs and confidence. `neighbors` validates requested edge types and applies the PIT predicate to every returned edge. Push predicates down in Spark without f-string interpolation of user values.

7. **Legacy integration — `api/services/graph_rag_engine.py:1`.** Keep existing public imports/tests compatible, but route structured fact lookup through the new API and clearly deprecate the old `graph_triples` path; do not silently mix non-PIT triples into fact answers. LLM synthesis may consume query results only as delimited, untrusted evidence and must preserve their provenance. If safe compatibility cannot be maintained, leave the legacy functions intact and additive, with a deprecation note—the new API is authoritative for facts.

8. **Strict agent tool — `agent/tools_retrieval.py` after `search_sec_filings` (currently around line 46).** Add a strict Pydantic input model (`extra='forbid'`, strict fields) and `query_sec_facts(ticker, metric, period, as_of, *, graph=None)`. Require an uppercase-able allow-listed ticker via `normalize_symbol`, bounded nonblank metric/period strings, and timezone-aware `datetime` (reject strings, integers, naive datetimes, extra args, and wrong types at runtime). The injectable `graph` supports offline tests; production defaults to the lazy Delta store. Return a JSON-safe envelope labelled `content_type: 'untrusted_tool_data'` with `results` and provenance; never concatenate tool values into instructions, execute values, or honor instruction-like content from labels/source text. Update the relevant agent tool registry/prompt if one exists, keeping this data/instruction boundary explicit.

9. **Ontology/docs — merge rather than overwrite concurrent files.** Once the ontology lane lands, make `ontology/table_semantics.yaml` describe the two table grains/PIT rule and `ontology/join_hints.yaml` describe `silver_sec_entities + silver_sec_sections -> gold_sec_kg_*` using `accepted_ts`; add only missing KG vocabulary to its chosen ontology file. State that `sec_kg/model.py` is canonical for executable enums. Update `docs/DATA_SCHEMAS.md` with exact columns and `docs/DEPLOYMENT.md` with the manual job and grants. Do not create a second conflicting vocabulary file if the parallel change already supplies one.

10. **Offline tests — new `tests/rag/test_sec_knowledge_graph.py` and `tests/rag/test_sec_kg_agent_tool.py` (new files, line 1), plus only targeted compatibility edits to existing graph tests.** Use tiny fixtures under `tests/rag/fixtures/` or in-test dictionaries; never depend on the gitignored 40 MB snapshots. Tests must import with `sys.modules['pyspark'] = None` (or an import blocker) and with provider credentials absent. Required red-before/green-after cases are below.

## Required tests (all must fail on the current branch before implementation)

- **ID stability:** the same semantic records in shuffled order and with benign case/whitespace variations yield identical IDs and byte-identical JSONL; a meaningful identity-field change changes the ID. Include a fixed expected SHA-256 test vector to catch algorithm drift.
- **PIT traversal:** create old/new filings and assert every result/neighbor edge has `valid_from <= as_of` and every returned provenance timestamp is `<= as_of`; querying before the first filing returns empty.
- **Restatement:** seed two different values for the same CIK/metric/start/end/unit at distinct acceptance times. Before the second acceptance return only the first; at/after it return the second with a `SUPERSEDES` reference, while storage still contains both facts. Also test equal-value refiling does not falsely mark a restatement.
- **Provenance:** every emitted node provenance entry and every edge has nonblank accession/chunk and UTC accepted time; verify deterministic accession fallback for company/event rows whose input chunk is null.
- **Typed argument rejection:** `query_sec_facts` rejects naive/string `as_of`, non-string period/metric, unknown/extra args, and an injection-shaped ticker before any store method is called. A source label containing `ignore previous instructions` is returned only inside the untrusted-data envelope.
- **CI-safe/no Spark:** hide `pyspark`, `databricks`, `langchain_openai`, and network credentials, then build/query JSONL and propose Q&A successfully. Assert default and zero-budget extraction call a bomb/fake client zero times.
- Add idempotency (second build has identical hashes/counts), malformed row rejection with manifest reason counts, endpoint integrity, enum validation, period grammar, deterministic series ordering, and Decimal precision tests.

Before changing code, record red evidence with:

```bash
python -m pytest -q tests/rag/test_sec_knowledge_graph.py tests/rag/test_sec_kg_agent_tool.py
```

After implementation run at minimum:

```bash
python -m pytest -q tests/rag/test_sec_knowledge_graph.py tests/rag/test_sec_kg_agent_tool.py
python -m pytest -q tests/rag/test_graph_rag_engine.py tests/rag/test_extract_graph_triples.py
python -m pytest -q tests/rag
python scripts/build_sec_knowledge_graph.py --entities evals/data/sec_entities.jsonl --corpus evals/data/sec_corpus.jsonl --output-dir /tmp/sec-kg-smoke --format jsonl
python scripts/build_sec_knowledge_graph.py --entities evals/data/sec_entities.jsonl --corpus evals/data/sec_corpus.jsonl --output-dir /tmp/sec-kg-smoke --format jsonl
```

Compare manifest hashes across the two smoke builds. The legacy extraction test currently uses `pytest.importorskip` because its script was removed; do not make that skip the only coverage of the new builder.

## Sizing and performance acceptance

The supplied inputs are approximately 20.5 MB entities + 20.1 MB corpus (49,687 + 10,720 rows). The offline build should stream inputs, retaining compact identity/provenance indexes rather than raw chunk text. Target peak RSS under 300 MB, full JSONL build under 30 seconds on a typical developer laptop, and warm offline indexed query p95 under 100 ms for `get_fact`/`risk_factors` and under 250 ms for bounded `neighbors` (default/max limit 100/1000). Measure with a small benchmark script or test marker and report observed Windows machine numbers in the verdict; thresholds may be non-gating when the full gitignored fixture is absent.

For 557 tickers, partition/cluster Delta primarily by ticker (or use liquid clustering on ticker plus node/edge type) and predicate-push `ticker`, `edge_type`, and `valid_from`; do not collect the graph to the driver. Expect output on the order of a few hundred thousand rows, not a Cartesian expansion. Use batched transforms/MERGEs, bounded neighbor limits, and incremental accession-based processing. Document when compaction/`OPTIMIZE` is appropriate, but do not schedule it in this task.

## Commit and handoff requirements

Work on Windows/offline, preserve LF line endings, and do not touch `.agents/dispatch.sh`. Commit in reviewable stages: (1) red tests/model, (2) deterministic offline build/query, (3) Delta job/agent integration/docs. Do not commit generated graph data or `/tmp` outputs. Write `.agents/mimo/VERDICT-rag-kg.md` containing commits, changed files, red/green command outputs, fixture hashes/counts, measured RSS/latency, known limitations, and explicit confirmation of zero paid calls in CI.

The MiMo verdict must include this **DeepSeek must check** list:

1. Stable-ID parity and deterministic bytes across order/reruns/backends.
2. PIT filtering occurs before restatement ranking and traversal; no future provenance leaks.
3. Restatement series key/value comparison is correct and retains both versions.
4. Every node/edge has real or explicitly synthetic provenance and valid endpoints.
5. Strict tool validation rejects wrong types/injection before backend access; output stays untrusted data.
6. Default/CI paths cannot import/call LLM, Spark, Databricks, or the network.
7. Delta MERGE is idempotent, manual job is unscheduled, and no driver-wide collect is used.
8. Full sample sizing, bounded neighbors, Q&A candidate citations, ontology merge, LF endings, and no `.agents/dispatch.sh` change.

