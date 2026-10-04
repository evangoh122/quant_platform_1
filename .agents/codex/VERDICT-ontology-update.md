===CODEX VERDICT START===

# CHANGES_REQUESTED

DeepSeek gate: ✓ `.agents/deepseek/VERDICT-ontology-update-check4.md` says `APPROVED`.

## Blocking finding

The knowledge-graph edge vocabulary contradicts its stated canonical implementation.

- ✗ [knowledge_graph.yaml](/home/jianj/code/qp1-onto/ontology/knowledge_graph.yaml:19) declares edges such as `COMPANY_FILED_FILING`, `FILING_HAS_SECTION`, `FACT_MEASURES_METRIC`, and `CHUNK_MENTIONS_COMPANY`.
- The canonical `origin/slice/rag-kg:sec_kg/model.py:38-51` instead permits `FILED`, `HAS_SECTION`, `INSTANCE_OF`, `SOURCED_FROM`, and others. `KgEdge.__post_init__` rejects names outside that enum at lines 305-307.
- The ontology omits canonical `SOURCED_FROM` and `SUPERSEDES`, even though `sec_kg/build.py:468-475` emits both.
- This is not merely stylistic documentation drift: [table_semantics.yaml](/home/jianj/code/qp1-onto/ontology/table_semantics.yaml:133) explicitly says `sec_kg/model.py` is canonical for edge types. The asserted ontology vocabulary therefore cannot describe valid stored `edge_type` values.
- The current tests do not compare KG node/edge declarations with the canonical enums; KG tables are skipped because their implementation is on another branch.

## Claim audit

I independently checked 22 claims spanning every ontology YAML:

1. ✓ Bronze OHLCV-day key is `(symbol, event_ts, timespan)`: [table_semantics.yaml:8](/home/jianj/code/qp1-onto/ontology/table_semantics.yaml:8), [refresh_bronze_equities.py:52](/home/jianj/code/qp1-onto/notebooks/refresh_bronze_equities.py:52).
2. ✓ Bronze options-day key is `(contract_symbol, event_ts, timespan)`: [table_semantics.yaml:13](/home/jianj/code/qp1-onto/ontology/table_semantics.yaml:13), [refresh_bronze_options.py:74](/home/jianj/code/qp1-onto/notebooks/refresh_bronze_options.py:74).
3. ✓ FED vintage key and PIT column exist in notebook DDL: [table_semantics.yaml:18](/home/jianj/code/qp1-onto/ontology/table_semantics.yaml:18), [refresh_bronze_fed.py:406](/home/jianj/code/qp1-onto/notebooks/refresh_bronze_fed.py:406).
4. ✓ CFTC raw natural key includes `source_dataset`: [table_semantics.yaml:24](/home/jianj/code/qp1-onto/ontology/table_semantics.yaml:24), [refresh_bronze_cot.py:312](/home/jianj/code/qp1-onto/notebooks/refresh_bronze_cot.py:312).
5. ✓ Silver OHLCV natural grain is the symbol/timestamp/timespan triple: [table_semantics.yaml:45](/home/jianj/code/qp1-onto/ontology/table_semantics.yaml:45), [01_silver_ohlcv.sql:59](/home/jianj/code/qp1-onto/silver/01_silver_ohlcv.sql:59), and dedup partition at line 63.
6. ✓ Gold OHLCV grain/key is `(symbol, feature_ts)`: [table_semantics.yaml:88](/home/jianj/code/qp1-onto/ontology/table_semantics.yaml:88), [01_gold_ohlcv_features.sql:96](/home/jianj/code/qp1-onto/gold/01_gold_ohlcv_features.sql:96).
7. ✓ OHLCV PIT availability is bar close, not bar start: [table_semantics.yaml:91](/home/jianj/code/qp1-onto/ontology/table_semantics.yaml:91), [01_gold_ohlcv_features.sql:22](/home/jianj/code/qp1-onto/gold/01_gold_ohlcv_features.sql:22).
8. ✓ Return formula uses `close/LAG(close,N)-1`: [metric_definitions.yaml:3](/home/jianj/code/qp1-onto/ontology/metric_definitions.yaml:3), [01_gold_ohlcv_features.sql:31](/home/jianj/code/qp1-onto/gold/01_gold_ohlcv_features.sql:31).
9. ✓ Realized-volatility formula uses trailing sample standard deviation of one-minute returns: [metric_definitions.yaml:7](/home/jianj/code/qp1-onto/ontology/metric_definitions.yaml:7), [01_gold_ohlcv_features.sql:61](/home/jianj/code/qp1-onto/gold/01_gold_ohlcv_features.sql:61).
10. ✓ `iv_atm` actually selects maximum open interest, then strike: [metric_definitions.yaml:31](/home/jianj/code/qp1-onto/ontology/metric_definitions.yaml:31), [02_gold_options_features.sql:102](/home/jianj/code/qp1-onto/gold/02_gold_options_features.sql:102).
11. ✓ Put/call ratio formula matches output SQL: [metric_definitions.yaml:35](/home/jianj/code/qp1-onto/ontology/metric_definitions.yaml:35), [02_gold_options_features.sql:187](/home/jianj/code/qp1-onto/gold/02_gold_options_features.sql:187).
12. ✓ COT crowding formula is the mean of the two z-scores: [metric_definitions.yaml:39](/home/jianj/code/qp1-onto/ontology/metric_definitions.yaml:39), [04_gold_cot_features.sql:132](/home/jianj/code/qp1-onto/gold/04_gold_cot_features.sql:132).
13. ✓ Bronze-to-silver OHLCV join keys exist on both sides: [join_hints.yaml:2](/home/jianj/code/qp1-onto/ontology/join_hints.yaml:2), [01_silver_ohlcv.sql:41](/home/jianj/code/qp1-onto/silver/01_silver_ohlcv.sql:41).
14. ✓ Entity-to-section chunk mapping is `source_chunk_id → chunk_id`: [join_hints.yaml:68](/home/jianj/code/qp1-onto/ontology/join_hints.yaml:68), [06_silver_sec_entities.sql:34](/home/jianj/code/qp1-onto/silver/06_silver_sec_entities.sql:34), [05_silver_sec_sections.sql:25](/home/jianj/code/qp1-onto/silver/05_silver_sec_sections.sql:25).
15. ✓ Both chunk columns originate from the same bronze `record_key`: same source lines as claim 14.
16. ✓ `regular_session_only` references an emitted Silver OHLCV column: [filters.yaml:29](/home/jianj/code/qp1-onto/ontology/filters.yaml:29), [01_silver_ohlcv.sql:52](/home/jianj/code/qp1-onto/silver/01_silver_ohlcv.sql:52).
17. ✓ SEC accepted-date filter uses the actual `accepted_ts` ingestion column: [filters.yaml:21](/home/jianj/code/qp1-onto/ontology/filters.yaml:21), [02_ingest_sec_edgar.py:166](/home/jianj/code/qp1-onto/notebooks/02_ingest_sec_edgar.py:166).
18. ✓ PIT comparison uses `information_available_ts <= prediction_ts`: [filters.yaml:25](/home/jianj/code/qp1-onto/ontology/filters.yaml:25), [pit_guard.py:5](/home/jianj/code/qp1-onto/gold/pit_guard.py:5).
19. ✓ CIK normalization is zero-padded to ten characters: [business_terms.yaml:7](/home/jianj/code/qp1-onto/ontology/business_terms.yaml:7), canonical `model.py:72-75`.
20. ✓ `chunk_id`/`source_chunk_id` relationship matches Silver transforms: [business_terms.yaml:44](/home/jianj/code/qp1-onto/ontology/business_terms.yaml:44), Silver evidence from claims 14-15.
21. ✓ KG node types match the canonical twelve-value `NodeType` enum: [knowledge_graph.yaml:5](/home/jianj/code/qp1-onto/ontology/knowledge_graph.yaml:5), canonical `model.py:19-31`.
22. ✗ KG edge types do not match the canonical `EdgeType` enum, as detailed in the blocking finding.
23. ✓ KG edge PIT invariant `valid_from == accepted_ts` is enforced: [knowledge_graph.yaml:4](/home/jianj/code/qp1-onto/ontology/knowledge_graph.yaml:4), canonical `model.py:305-313`.

## Tests

- Focused command: `24 passed, 22 skipped in 3.76s`.
- Full suite excluding `tests/lakebase`: stalled twice in this sandbox. The bounded rerun reached 180 seconds and exited `124` without producing a test summary.

Mutation checks against isolated `/tmp` copies:

- ✓ Phantom key: failed `test_table_keys_exist_in_sql_schema[silver_ohlcv]`.
- ✓ Wrong bronze key: failed `test_bronze_market_keys_match_notebook_constants`.
- ✓ Non-existent filter column: failed `test_filter_columns_exist_in_sql_schema[regular_session_only]`.
- ✓ Duplicate normalized term: failed `test_no_duplicate_terms`.

## Skip audit

All 22 skips emit an explicit reason. They comprise:

- 16 tables lacking DDL or a defining SQL transform recognized by this branch’s parser.
- 4 SQL filters whose referenced tables lack such a local schema.
- 2 rule-only filters with no SQL columns.

The skips are mechanically justified by the test’s stated scope and are individually documented. Coverage is nevertheless incomplete: notably, `gold_sec_kg_nodes` and `gold_sec_kg_edges` are skipped, which allowed the blocking canonical-vocabulary mismatch to pass.

Required resolution: reconcile `knowledge_graph.yaml` with the canonical `NodeType`/`EdgeType` vocabulary and add a contract test against those canonical enums when the KG implementation is available.

===CODEX VERDICT END===
