===VERDICT START===
# VERDICT: ontology-update (check4) — DeepSeek (Schema & API Contract lane)

**Status:** APPROVED
**Round:** 4
**Branch:** `slice/ontology-update` (`900c319`, request `48eda7a`)

Read-only re-check. The round-4 commit fixes all three round-3 blocking
findings and the two non-blocking notes it was asked to address. The new
notebook-constant test is real (I mutated `event_date` as a bronze key and both
parametrizations fail). Nothing blocking remains.

## Round-4 re-verification (all resolved)

1. **bronze_ohlcv_day grain/key** — [table_semantics.yaml:8-9] now
   `keys: [symbol, event_ts, timespan]`, grain "…; event_date is derived".
   Matches `notebooks/refresh_bronze_equities.py:50-52` ("Natural key for both
   market tables", `KEY_COLUMNS = ["symbol", "event_ts", "timespan"]`), used for
   `dropDuplicates`/left-anti-join on the day table (L479, L482); `event_date`
   is derived via `event_ts.date()` (L182). **Correct.**
2. **bronze_options_day grain/key** — [table_semantics.yaml:13-14] now
   `keys: [contract_symbol, event_ts, timespan]`. Matches
   `notebooks/refresh_bronze_options.py:74` (`DAY_KEY_COLUMNS =
   ["contract_symbol", "event_ts", "timespan"]`), docstring "key:
   (contract_symbol, event_ts, timespan)" (L11); `event_date` derived via
   `F.to_date(event_ts)` (L481). **Correct.**
3. **KG additions** — [join_hints.yaml:43-54] now use the correct
   `left_table`/`right_table`/`keys` structure (the round-3 `KeyError` risk is
   gone). `keys: [source_chunk_id, chunk_id]` maps
   `source_chunk_id` → `silver_sec_entities` (`silver/06:34`, `record_key AS
   source_chunk_id`) and `chunk_id` → `silver_sec_sections` (`silver/05:25`,
   `record_key AS chunk_id`); both are the same bronze `record_key`, so the
   two-name key list is the correct left/right pairing. The
   `gold_sec_kg_nodes`/`gold_sec_kg_edges` semantics
   [table_semantics.yaml:122-133] are accurate against
   `origin/slice/rag-kg:sec_kg/model.py`: `KgNode` (`node_id`, `node_type`,
   provenance `accepted_ts`) and `KgEdge` (`edge_id`, `edge_type`,
   `valid_from == accepted_ts` enforced in `KgEdge.__post_init__`).
   **Correct.**

## Round-3 non-blocking notes now addressed

- **bronze_cftc_fut `source_dataset`** — [table_semantics.yaml:24-25] now
  `keys: [source_dataset, CFTC_Contract_Market_Code, report_date]`, matching the
  ingester's natural key `["source_dataset", contract_code_col, "report_date"]`
  (`notebooks/refresh_bronze_cot.py:314,333,466,508`) where
  `contract_code_col` resolves to `CFTC_Contract_Market_Code` (L238). **Correct.**
- **External-contract coverage** — the new
  `test_bronze_market_keys_match_notebook_constants` closes the gap that let the
  two bronze day-table findings through: both `KEY_COLUMNS` and
  `DAY_KEY_COLUMNS` are now asserted against the ontology keys.
- **SUPERSEDES tension** — `knowledge_graph.yaml` pit_rule now states restatement
  facts are "linked by SUPERSEDES edges", consistent with
  `sec_kg/build.py:472-474` (emits `EdgeType.SUPERSEDES`) and `model.py:51`.
  See non-blocking note 1 for the remaining edge-vocabulary drift.

## Non-blocking notes

- **Edge vocabulary drift between `knowledge_graph.yaml` and `sec_kg/model.py`.**
  The YAML enumerates 15 edges (9 deterministic + 6 LLM); `model.py`'s
  `EdgeType` enum has 13 (9 + HAS_SEGMENT/HAS_PRODUCT/HAS_CUSTOMER/SUPERSEDES).
  The YAML `edge_types` list does not enumerate `SUPERSEDES` (now referenced by
  the pit_rule and the `gold_sec_kg_edges` transform) nor `SOURCED_FROM`, while
  `CHUNK_MENTIONS_COMPANY` and the three `*_REPORTS_FACT` / `*_RELATED_TO_EVENT`
  LLM edges have no `model.py` counterpart. `schema_ref` correctly delegates
  canonical edge types to `model.py`, and `deterministic_counts` /
  `optional_llm_counts` are internally self-consistent, so this is documentation
  drift, not a schema error. Recommend reconciling the edge list when the rag-kg
  lane lands.
- **`gold_sec_kg_nodes` / `gold_sec_kg_edges` are not schema-guarded on this
  branch.** Both are skipped by `test_table_keys_exist_in_sql_schema` (no
  defining SQL under `silver/`/`gold/`), and they are not in
  `EXTERNAL_SCHEMA_CONTRACTS`. Their `[node_id]` / `[edge_id]` keys are verified
  here by hand against `model.py`, but no test enforces them.
- **`cot_crowding_score` naming** (pre-existing): metric key is
  `cot_crowding_score` while the gold column is `crowding_score`
  (`gold/04:132`); formula matches.

## Mutation check (in `/tmp/qp1-mut*`, worktree untouched)

```
BASELINE:                                    24 passed, 22 skipped
MUTATION event_date_keys (day tables +event_date):
  FAILED test_bronze_market_keys_match_notebook_constants[bronze_ohlcv_day-...]
  FAILED test_bronze_market_keys_match_notebook_constants[bronze_options_day-...]
  2 failed
MUTATION phantom_key (silver_ohlcv keys + phantom_key):
  FAILED test_table_keys_exist_in_sql_schema[silver_ohlcv]
MUTATION filter_column (regular_session_only + phantom_flag):
  FAILED test_filter_columns_exist_in_sql_schema[regular_session_only]
MUTATION join_column (lineage key + phantom_join_col):
  FAILED test_join_columns_exist_in_sql_schema
```

The requested `event_date` mutation fails both day-table tests, and the phantom
key / filter column / join column mutations each fail their intended test. The
22 skips are legitimate: they are bronze tables with no DDL/transform in
`silver/`/`gold/` (guarded now by the notebook-constant and fed-DDL tests where
applicable), plus `gold_sec_kg_nodes`/`gold_sec_kg_edges` (rag-kg branch) and
rule-only filters.

## Checks run

- `python3 -m pytest tests/test_ontology.py -q` → 24 passed, 22 skipped
- `python3 -m pytest tests/test_ontology.py -rs -q` → all skips accounted for;
  none suspicious beyond the coverage notes above
- mutations event_date_keys / phantom_key / filter_column / join_column → each
  fails its intended test
- `grep` of `notebooks/refresh_bronze_equities.py` / `refresh_bronze_options.py`
  / `refresh_bronze_cot.py` key constants vs. `table_semantics.yaml`
- `git show origin/slice/rag-kg:sec_kg/model.py` + `sec_kg/build.py` →
  node/edge vocabulary, `valid_from == accepted_ts`, and `SUPERSEDES` emission
  verified
===VERDICT END===
