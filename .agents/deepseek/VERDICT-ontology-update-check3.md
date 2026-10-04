===VERDICT START===
# VERDICT: ontology-update (check3) — DeepSeek (Schema & API Contract lane)

**Status:** CHANGES_REQUESTED
**Round:** 3
**Branch:** `slice/ontology-update` (`77ce9f2`, request `42ff5e1`)

Read-only re-check. The round-3 commit (`77ce9f2`) fixes every round-2 blocking
finding correctly, and the new vintage-grain test is real (I mutated it). Two
remaining factual errors survive in `table_semantics.yaml`, and the proposed KG
additions in `.agents/requests/kg_ontology_additions.diff` are not accurate
enough to land as-is. Details below.

## Round-3 re-verification (all resolved)

1. **bronze_fed_series vintage grain** — [table_semantics.yaml:17-22] now
   `keys: [series_id, observation_date, vintage_date]`, grain "one observation
   vintage per (...)", plus `latest_as_of_rule`. Matches
   `notebooks/refresh_bronze_fed.py`: DDL `vintage_date DATE NOT NULL` (L410),
   `information_available_ts TIMESTAMP NOT NULL` (L411); `select_new_rows`
   appends a new row whenever a re-fetched value differs from the latest stored
   vintage (L302-332); `information_available_ts = ingest_ts` for `revised_macro`
   and `_ny_available_ts(...)` only for `market_rate` (L279-282). **Correct.**
2. **gold_trading_signals status** — [table_semantics.yaml:134] now
   `status_note` instead of `status_enum`. Matches
   `db/migrations/001_operational_schema.sql:49` (`status TEXT NOT NULL DEFAULT
   'ACTIVE'`, no CHECK on status; only `direction` L43-44 and `probability` L47
   are constrained). **Correct.**
3. **silver_sec_entities keys** — [table_semantics.yaml:80-82] now
   `[accession_number, entity_type, entity_key, entity_value, period_end]`,
   matching the MERGE key in `silver/06_silver_sec_entities.sql:122-126`.
   **Correct.**
4. **KG CHUNK_SUPPORTS_FACT removed** — [knowledge_graph.yaml:2-3]
   `deterministic_counts: {node_types: 9, edge_types: 9}` + `optional_llm_counts:
   {node_types: 3, edge_types: 6}`. Recount: 9 deterministic edges + 6 LLM edges
   = 15; 12 node types total. Self-consistent. **Correct.**
5. **Restatement honesty** — pit_rule now states the graph does not model
   supersession/valid-to and consumers must resolve restatements. Honest for the
   silver-derived deterministic graph. **Correct** (see non-blocking note 3 for
   the tension with the rag-kg build).
6. **put_call_ratio case note** — [metric_definitions.yaml:37] note is accurate:
   `gold/02_gold_options_features.sql:73-74` compares `right = 'PUT'`/`'CALL'`
   (uppercase) while `notebooks/refresh_bronze_options.py:_shape_day` writes
   `'call'`/`'put'` (L476-479). The metric would compute NULL (0/0). Note is
   correct, and it is a gold-SQL bug, not an ontology error.
7. **New test** `test_bronze_fed_series_keys_match_notebook_ddl_vintage_grain`
   parses the notebook DDL and asserts `keys == {series_id, observation_date,
   vintage_date}`. Real: it caught a phantom vintage key (mutation D below).

## Blocking findings

1. **bronze_ohlcv_day grain/key mis-stated.** [table_semantics.yaml:8] says
   `keys: [symbol, event_date]`, grain "one daily bar per (symbol, event_date)".
   The ingester's natural key for **both** market tables is
   `(symbol, event_ts, timespan)`:
   `notebooks/refresh_bronze_equities.py:50-52` (`# Natural key for both market
   tables`, `KEY_COLUMNS = ["symbol", "event_ts", "timespan"]`), used for
   dropDuplicates/left-anti-join on the day table too (L479, L482). The minute
   table in the same registry is keyed `[symbol, event_ts, timespan]`
   [table_semantics.yaml:4], so the day table using `event_date` is inconsistent
   and wrong. → Failure: an NL "grain" query or validator deduplicating on
   `(symbol, event_date)` does not match the physical dedup key and can collapse
   or mis-identify rows.

2. **bronze_options_day grain/key mis-stated.** [table_semantics.yaml:14] says
   `keys: [contract_symbol, event_date]`. The ingester uses
   `DAY_KEY_COLUMNS = ["contract_symbol", "event_ts", "timespan"]`
   (`notebooks/refresh_bronze_options.py:74`, docstring "key: (contract_symbol,
   event_ts, timespan)" L11). `event_date` is a derived column, not the key.
   → Same failure mode as (1). Note the test suite does not catch either: both
   bronze tables have no DDL in `silver/`/`gold/` so
   `test_table_keys_exist_in_sql_schema` skips them.

3. **Proposed KG additions (`kg_ontology_additions.diff`) are not accurate as
   written — do not add as-is.** The `table_semantics.yaml` entries
   (`gold_sec_kg_nodes` / `gold_sec_kg_edges`) are accurate against
   `sec_kg/model.py` (KgNode: `node_id`/`node_type`/provenance `accepted_ts`;
   KgEdge: `edge_id`/`edge_type`/`valid_from == accepted_ts`, enforced in
   `KgEdge.__post_init__`). But the `join_hints.yaml` lineage entries are wrong:
   - `silver_sec_entities + silver_sec_sections -> gold_sec_kg_nodes` key
     `[cik, accession_number, source_chunk_id]`: `source_chunk_id` is **not a
     column** of `silver_sec_sections` (it is `chunk_id`, `silver/05:25`); only
     `silver_sec_entities` has `source_chunk_id` (`silver/06:34`). The chunk
     join is `entity.source_chunk_id ↔ section.chunk_id` (both = bronze
     `record_key`).
   - `... -> gold_sec_kg_edges` key `[src_id, edge_type, dst_id, accession_number,
     source_chunk_id]` mixes **output** columns (`src_id`, `edge_type`, `dst_id`
     are gold_sec_kg_edges fields, not source-table columns) with provenance
     columns. Not a join key between the two source tables.
   - Structural mismatch: these entries use `key` (singular) with no
     `left_table`/`right_table`/`keys`, unlike every existing `lineage` entry.
     `test_join_columns_exist_in_sql_schema` reads `spec["left_table"]` and
     `spec["keys"]` for `lineage`, so adding these verbatim raises `KeyError`.

## Non-blocking notes

- **External-contract coverage still partial.** `EXTERNAL_SCHEMA_CONTRACTS`
  (tests/test_ontology.py:15-20) guards only `gold_regime_features` and
  `gold_tradable_universe`; the new fed test guards `bronze_fed_series`. The
  remaining skipped-but-unverified tables are exactly where findings 1-2 live:
  `bronze_ohlcv`, `bronze_ohlcv_day`, `bronze_options_day`, `bronze_cftc_fut`,
  `bronze_cot`, `bronze_sec_filings`, `bronze_sec_filings_v2`,
  `silver_ohlcv_quarantine`, `gold_sec_features`, `gold_sec_chunk_embeddings`,
  `gold_trading_signals`. Recommend extending the notebook-DDL parsing approach
  (the fed test) to the bronze day tables.
- **bronze_cftc_fut key omits `source_dataset`.** The ingester dedups on
  `["source_dataset", contract_code_col, "report_date"]`
  (`notebooks/refresh_bronze_cot.py:312-316,466-467`). `source_dataset` is
  constant within the futures-only table, so `[report_date,
  CFTC_Contract_Market_Code]` is effectively unique; noted for completeness.
- **SUPERSEDES tension.** `knowledge_graph.yaml` pit_rule now says restatement
  supersession is unmodelled, but the rag-kg build's `gold_sec_kg_edges` emits
  `SUPERSEDES` edges (model.py `EdgeType.SUPERSEDES`; smoke output confirms them),
  and the diff's own edges transform says "SUPERSEDES edges for restatements".
  When Codex adds the KG tables it should reconcile this sentence so the ontology
  does not contradict the table it registers.
- **`cot_crowding_score` naming.** The metric is named `cot_crowding_score` but
  the gold column is `crowding_score` (`gold/04:132`); formula matches.

## Mutation check of the schema-parsing tests (in /tmp, worktree untouched)

```
BASELINE:                          22 passed, 20 skipped
MUTATION A (phantom key silver_ohlcv + phantom_key):
  FAILED test_table_keys_exist_in_sql_schema[silver_ohlcv]
  E   silver_ohlcv has no columns ['phantom_key']
MUTATION B (filter col regular_session_only + phantom_flag):
  FAILED test_filter_columns_exist_in_sql_schema[regular_session_only]
MUTATION C (join col lineage + phantom_join_col):
  FAILED test_join_columns_exist_in_sql_schema
MUTATION D (phantom fed vintage key):
  FAILED test_bronze_fed_series_keys_match_notebook_ddl_vintage_grain
  E   assert keys == {'series_id', 'observation_date', 'vintage_date'}
```

All four mutation classes are caught. The 20 skips are legitimate (no DDL or
defining transform in `silver/`/`gold/` for those tables), but — as noted — the
two bronze day tables are skipped precisely because their keys are not covered
by the external-contract test, which is what let findings 1-2 through.

## Checks run

- `python3 -m pytest tests/test_ontology.py -q` → 22 passed, 20 skipped
- `python3 -m pytest tests/test_ontology.py -rs -q` → 14 table-key skips +
  6 filter skips; none suspicious beyond the coverage gap above
- mutation A/B/C/D (above) → each fails its intended test
- `git show origin/slice/rag-kg:sec_kg/model.py` → node/edge vocabulary and
  identity helpers reviewed (KgNode/KgEdge fields, `valid_from == accepted_ts`)
- `git show origin/slice/strategy-residual-reversion:gold/06...`/`gold/07...` →
  `med_adv_60d`, `breadth_regime`, `rsp_spy_ratio_zscore_252` verified
- `strategies/residual_reversion.py::compute_residuals` (branch) + `ml/evaluate.py`
  → `residual`, `s_score` (L=5, sigma 60d min_obs=48), `deflated_sharpe_ratio`
  (Bailey/López de Prado), `drawdown` all verified against formulas
===VERDICT END===
