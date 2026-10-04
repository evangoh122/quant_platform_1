===VERDICT START===
# VERDICT: ontology-update (check5) — DeepSeek (Schema & API Contract lane)

**Status:** APPROVED
**Round:** 5
**Branch:** `slice/ontology-update` (`175948a`, request `7a014bb`)

Read-only re-check. The round-5 commit aligns the KG node/edge names with the
canonical `origin/slice/rag-kg:sec_kg/model.py` enums, adds
`SOURCED_FROM`/`SUPERSEDES` plus the filing-level citation rule, and adds an
enum-sync test backed by a snapshot fixture. I verified the names equal the
enums exactly, the snapshot equals `model.py`, and the new test fails on
phantom-node and phantom-edge mutations. Nothing blocking remains.

## Round-5 re-verification

1. **Node names == `NodeType` enum exactly.**
   `knowledge_graph.yaml` `node_types` keys are the 12 canonical values
   (Company, Filing, Section, Chunk, XbrlFact, Metric, Period, RiskFactor,
   Event, Segment, Product, Customer). Programmatic diff against
   `_enum_values("NodeType")` from `git show origin/slice/rag-kg:sec_kg/model.py`
   → sets equal (12/12). The 9 `deterministic` + 3 `optional_llm` split matches
   `deterministic_counts`/`optional_llm_counts`. **Correct.**
2. **Edge names == `EdgeType` enum exactly.**
   13 edges (FILED, HAS_SECTION, HAS_CHUNK, REPORTED_FACT, INSTANCE_OF,
   FOR_PERIOD, SOURCED_FROM, DISCLOSED_RISK, REPORTED_EVENT, HAS_SEGMENT,
   HAS_PRODUCT, HAS_CUSTOMER, SUPERSEDES). Programmatic diff vs
   `_enum_values("EdgeType")` → sets equal (13/13). 10 deterministic + 3
   optional matches the counts. **Correct.**
3. **Snapshot == `model.py`.**
   `tests/fixtures/sec_kg_enum_snapshot.yaml` `node_types` (12) and
   `edge_types` (13) are set-equal to the `NodeType`/`EdgeType` string values
   in `model.py`. **Correct.**
4. **Edge endpoints & citation semantics == `sec_kg/build.py`.**
   `FILED` Company→Filing, `HAS_SECTION` Filing→Section, `HAS_CHUNK`
   Section→Chunk, `REPORTED_FACT` Company→XbrlFact, `INSTANCE_OF`
   XbrlFact→Metric, `FOR_PERIOD` XbrlFact→Period, `SOURCED_FROM`
   {XbrlFact,RiskFactor,Event}→Chunk, `DISCLOSED_RISK` Filing→RiskFactor,
   `REPORTED_EVENT` Filing→Event, `HAS_SEGMENT`/`HAS_PRODUCT`/`HAS_CUSTOMER`
   Company→{Segment,Product,Customer}, `SUPERSEDES` XbrlFact→XbrlFact. Each
   matches the corresponding `_add_edge(...)` call in `build.py`. `SOURCED_FROM`
   is emitted only when `citation_level == "chunk"`; when `"filing"`, `build.py`
   sets `properties["source_url"] = _edgar_filing_url(...)` and creates no
   synthetic Chunk — matching the `citation_rule`. `SUPERSEDES` is emitted only
   when a later accepted fact for the same series has a different value
   (`build.py` `prev_value != value_text` guard). **Correct.**
5. **Enum-sync test catches mutations.**
   Mutation A (phantom edge `PHANTOM_EDGE`) → `test_knowledge_graph_vocabulary_matches_canonical_sec_kg_enums` FAILS
   ("Extra items in the left set: 'PHANTOM_EDGE'"). Mutation B (phantom node
   `PhantomNode`) → same test FAILS ("Extra items ... 'PhantomNode'"). Both
   restored via `git checkout`; working tree clean. **Correct.**

## Non-blocking notes

- **Snapshot is a cold fallback.** `_canonical_kg_vocabulary()` prefers a local
  `sec_kg/model.py`, then `git show origin/slice/rag-kg:sec_kg/model.py`, and
  only then the snapshot. In an environment where both the local file and the
  remote ref are absent, a stale snapshot would silently pass. It currently
  matches `model.py`, so no action needed now; consider a CI step that asserts
  snapshot freshness if the rag-kg lane ever rewrites its enums.
- **`SOURCED_FROM.from` is a 3-element list** (`[XbrlFact, RiskFactor, Event]`),
  not a single type. The test compares names (keys), not the `from`/`to`
  endpoints, so this list is not schema-guarded; verified by hand against
  `build.py` (see item 4).

## Checks run

- `python3 -m pytest tests/test_ontology.py -q` → 25 passed, 22 skipped
- `python3 -m pytest tests/test_ontology.py::test_knowledge_graph_vocabulary_matches_canonical_sec_kg_enums -q` → pass
- programmatic set-diff of `knowledge_graph.yaml` node/edge keys vs
  `NodeType`/`EdgeType` enum values → equal (12 nodes, 13 edges)
- programmatic set-diff of `tests/fixtures/sec_kg_enum_snapshot.yaml` vs
  `model.py` enums → equal
- `git show origin/slice/rag-kg:sec_kg/model.py` + `sec_kg/build.py` →
  endpoints, `valid_from == accepted_ts`, `SOURCED_FROM`/`SUPERSEDES` emission,
  `citation_level` chunk/filing semantics verified
- mutation `PHANTOM_EDGE` → enum-sync test FAILS; mutation `PhantomNode` →
  enum-sync test FAILS; both reverted, `git diff --stat` clean
===VERDICT END===
