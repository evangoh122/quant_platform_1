===VERDICT START===
# VERDICT: rag-kg — DeepSeek (Schema & API Contract Engineer)
**Status:** CHANGES_REQUESTED
**Round:** 1

Two correctness defects block approval: (1) instant-period XBRL facts are
silently dropped because a JSON `null` period_start becomes the string `"None"`,
losing 11,579 of 43,722 facts (26.5%); (2) the provenance/citation chain for
XBRL facts (and events) is unresolvable — `query_sec_facts` returns a
`source_chunk_id` that does not resolve to any corpus chunk, so answers cannot
be cited back to filing text. All 66 committed tests are green, but the fixture
set never exercises `period_start: null`, so the suite masks defect (1).

## Blocking findings

- [sec_kg/build.py:364-372] Instant-period XBRL facts dropped. `period_start_raw
  = str(row.get("period_start", ""))` maps JSON `null` to the string `"None"`,
  then `iso_date("None")` raises `ValueError` and the whole row is rejected.
  → In `evals/data/sec_entities.jsonl` exactly 11,579 of 43,722 `xbrl_fact` rows
  have `period_start: null` (instant facts: Assets, Liabilities, etc.). All are
  discarded; the offline build emits 32,143 XbrlFact nodes (== duration count)
  instead of 43,722. Direct repro (built with a single instant fact) yields 0
  XbrlFact nodes. Violates CHECK item 2 ("instant vs duration periods … parsed
  correctly"). No test uses `period_start: null`, so the green suite misses it.

- [sec_kg/build.py:106-107] Fact provenance not resolvable to filing text.
  `resolve_source_chunk_id` returns an entity's present-but-unresolvable
  `source_chunk_id` verbatim (`synthetic=False`) without checking the corpus.
  In the supplied data, 0 of 43,722 `xbrl_fact` `source_chunk_id` values appear
  in `sec_corpus.jsonl` (only the 1,457 risk-factor ids do; corpus covers 128 of
  1,026 accessions). → Of 35,341 `SOURCED_FROM` edges, only 1,457 point at a
  real chunk; every fact/event citation is a dead reference. CHECK item 2's
  "spot-check 10 real facts against their source_chunk_id text" is impossible,
  and CHECK item 4's "answers can cite sources" fails for facts. The
  accession→lexicographic-chunk→`filing:<accession>` fallback is never reached
  because the raw id is treated as valid. The fact's provenance is also not
  marked `synthetic_source`, while the Chunk node it points to is — an
  inconsistency.

## Non-blocking notes

- [scripts/build_sec_knowledge_graph.py:135,189] Manifest rejection reporting is
  wrong: `rejected_row_count = len(entities) - len(nodes)` yields **-33911** (a
  negative number), and `rejection_reasons` is hard-coded `{}`. `build_graph`
  already tracks `BuildStats` reasons but never returns/surfaces them, so the
  spec-required "rejected-row counts/reasons" field is non-functional.
- [scripts/build_sec_knowledge_graph.py:75-77] `--as-of` is parsed and written
  to the manifest but never applied to anything (build is full-history, so this
  is arguably by design, but a no-op flag is misleading).
- [sec_kg/build.py:386] Version sort key is `(accepted_ts, accession)`; the spec
  requires `(accepted_ts, accession_number, node_id)`. Ties (same accession +
  accepted_ts, differing value) are broken by stable-sort/input order, so output
  bytes could depend on input order in that edge case.
- Ontology alignment (CHECK item 6): `sec_kg/model.py` does **not** match
  `ontology/knowledge_graph.yaml` on `slice/ontology-update` (see list below).
  model.py faithfully implements BUILD-rag-kg.md §canonical model, which the
  spec declares canonical ("State that sec_kg/model.py is canonical for
  executable enums"); reconciliation must happen at merge time. The rag-kg
  branch correctly avoided creating a second vocabulary file, but did not update
  `ontology/table_semantics.yaml`/`join_hints.yaml` with the two KG grains/PIT
  rule as item 9 required.
- [api/services/graph_rag_engine.py] Legacy `graph_triples` path left untouched
  with no deprecation note (BUILD item 7's fallback requires "leave intact …
  with a deprecation note"). New `query_sec_facts`/`SecKnowledgeGraph` are
  correctly authoritative and separate, so no non-PIT mixing — cosmetic gap.
- Performance: full JSONL build is fast (7.5–10.7 s, <30 s target) and
  byte-idempotent, but peak RSS measured **~634,672 KB (~620 MB)** vs the 300 MB
  target, because the CLI loads all entities + full corpus text + full graph into
  memory instead of streaming. Non-gating per spec but worth flagging.
- `normalize_unit`/`str(None)` latent issue: a `null` `entity_unit` would become
  the literal unit `"NONE"` (no `null` unit present in current data).

### Ontology vs model.py — every mismatch (CHECK item 6)

Node type **names** (12: 9 deterministic + 3 optional LLM) match exactly.
Everything else diverges:

1. Edge type names: model.py uses verb-only names (`FILED`, `HAS_SECTION`, …);
   ontology uses `SRC_VERB_DST` (`COMPANY_FILED_FILING`, `FILING_HAS_SECTION`, …).
   Zero of 13 model.py edges match zero of 15 ontology edges verbatim.
2. `REPORTED_FACT`: model.py = Company→XbrlFact (per BUILD spec); ontology's
   `FILING_REPORTS_FACT` = Filing→XbrlFact.
3. Ontology has `CHUNK_MENTIONS_COMPANY` (Chunk→Company); model.py has none.
4. model.py has `SOURCED_FROM` (Fact/Risk/Event→Chunk); ontology has none.
5. model.py has `SUPERSEDES` (Fact→Fact); ontology states "the graph does not
   model supersession".
6. Ontology has 3 optional edges (`SEGMENT_REPORTS_FACT`, `PRODUCT_REPORTS_FACT`,
   `CUSTOMER_RELATED_TO_EVENT`) with no model.py equivalent (model.py optional
   edges are only `HAS_SEGMENT`/`HAS_PRODUCT`/`HAS_CUSTOMER`).
7. Node identity keys differ: ontology `XbrlFact.key = [accession_number,
   entity_key, entity_unit, period_start, period_end]` (no value, no cik, no
   source_chunk_id) vs model.py `xbrl_fact_id = (v1, xbrl_fact, cik, accession,
   metric, period_start, period_end, unit, canonical_value, source_chunk_id)`;
   ontology `Filing.key = accession_number` vs model.py `(cik, accession)`;
   `RiskFactor/Event.key = [accession_number, entity_key]` vs model.py
   `(cik, accession, source_chunk_id, key, value)`.
8. Ontology header claims `edge_types: 9` deterministic + 6 optional = 15;
   model.py has 13. The CHECK text's "10 edges" does not match the file (it says
   9).

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/rag` → **pass** (364 passed, 19 skipped, 1 warning)
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → **pass** (643 passed, 67 skipped)
- `python3 -m pytest --collect-only -q tests/rag/test_sec_knowledge_graph.py tests/rag/test_sec_kg_agent_tool.py` → **66 tests** (matches claim)
- `python3 scripts/build_sec_knowledge_graph.py --entities … --corpus … --output-dir /tmp/sec-kg-smoke --format jsonl` ×2 → **pass** (83,598 nodes / 135,805 edges; second run byte-identical nodes+edges; manifest identical except build_timestamp)
- Restatement at 3 `as_of` (synthetic ACC-1/ACC-2): before→`None`, between→`10000000000` (not restatement), after→`12000000000` (is_restatement=True, supersedes set, both retained) → **pass** (PIT/restatement logic correct)
- ID collisions: 83,598 unique node_ids, 135,805 unique edge_ids → **pass**
- Provenance completeness (nonblank accession/chunk/UTC on every node+edge; valid_from==accepted_ts) → **pass** on fields, **fail** on resolvability (see blocking #2)
- `query_sec_facts`: naive/string/int `as_of`, non-string metric/period, extra kwarg, injection ticker (`'; DROP TABLE --`) all rejected before store access; `content_type='untrusted_tool_data'` → **pass** (tests + `extra='forbid'` pydantic model)
- LLM enrichment: default/zero-budget returns `[]` with zero client calls; no network/Spark in tests → **pass**
- `resources/jobs.yml:32` `sec_knowledge_graph_build`: no `schedule` block, passes `--catalog`/`--schema` explicitly → **pass**
- Instant-fact bug repro (`period_start: null`) → **fail** (0 XbrlFact nodes)
- Fact `source_chunk_id` resolvable in corpus → **fail** (0/43,722)
- Peak RSS (full build) → 634,672 KB (~620 MB; 300 MB target, non-gating)
===VERDICT END===
