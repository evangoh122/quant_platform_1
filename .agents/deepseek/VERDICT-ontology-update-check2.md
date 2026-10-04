===VERDICT START===
# VERDICT: ontology-update (check2) — DeepSeek (Schema & API Contract lane)

**Status:** CHANGES_REQUESTED
**Round:** 2
**Branch:** `slice/ontology-update` (`c63df5f`)

Read-only re-check. All 7 round-1 blocking findings are resolved; this verdict
confirms the fixes and reports two remaining factual errors plus coverage gaps.

## Round-1 re-verification (all fixed)

1. join_hints.yaml lineage — now `bronze_cftc_fut_to_silver_cot_positions`,
   `bronze_sec_filings_v2_to_silver_sec_sections` / `..._to_silver_sec_entities`.
   Correct (`silver/07:77`, `silver/05:34`, `silver/06:36,64,88,116`).
2. gold_regime_features keys `[trade_date]`, gold_tradable_universe keys
   `[symbol, trade_date]` — match `gold/07` and `gold/06` CREATE TABLE.
3. filters.yaml `point_in_time_universe` now predicates `u.trade_date` (not
   `as_of_date`). Correct.
4. iv_atm now = max-open-interest selection, `open_interest DESC NULLS LAST,
   strike` — matches `gold/02:102-109`.
5. s_score now = `s_cum / sigma`, L=5 cumulative residual over 60-day estimation
   sigma; `min_obs = ceil(0.8*60)=48`. Matches
   `strategies/residual_reversion.py::compute_residuals` (`_trailing_std(window=60,
   min_periods=48)`, `s_cum = residual.rolling(5).sum()`).
6. drawdown / deflated_sharpe / residual / s_score now point at
   `ml/evaluate.py:build_backtest` / `:deflated_sharpe_ratio` /
   `strategies/residual_reversion.py` instead of `gold_*` tables. Correct.
7. KG Segment/Product/Customer + their edges are marked
   `optional_llm_enrichment (off by default)`; `deterministic_counts` corrected to
   `{9, 10}` (12 nodes − 3 LLM, 16 edges − 6 LLM). Coherent.

## Blocking findings

1. **bronze_fed_series grain and keys are wrong — the table is a vintage
   history.** [table_semantics.yaml:17-21] states grain "One observation per
   (series_id, observation_date)" and `keys: [series_id, observation_date]`.
   `notebooks/refresh_bronze_fed.py` stores *multiple vintages* per observation:
   the DDL makes `vintage_date DATE NOT NULL`
   (`_create_table_if_absent`, lines 401-419) and `select_new_rows` (lines
   302-332) appends a **new row** whenever a re-fetched value differs from the
   latest stored vintage ("A candidate is new ... or its value differs from the
   latest stored vintage"). → Failure scenario: the NL semantic registry reports
   bronze_fed_series as keyed by `(series_id, observation_date)`, so a "latest
   CPI" query silently returns a stale/duplicated row; the true grain is
   `(series_id, observation_date, vintage_date)`.
   Related: the `freshness` note "Per source release calendar" is only true for
   `revision_class == market_rate`; for `revised_macro` (CPIAUCSL, UNRATE, ...)
   the code sets `information_available_ts = ingest_ts` (line 282), not a release
   calendar.

2. **gold_trading_signals `status_enum` is undocumented in the live schema.**
   [table_semantics.yaml:133] lists `status_enum: [ACTIVE, EXPIRED, CONSUMED]`.
   The only live definition is the operational `signals` table
   (`db/migrations/001_operational_schema.sql:42-49`), which has `status TEXT
   DEFAULT 'ACTIVE'` and **no CHECK constraint** for status, and only
   `direction IN ('LONG','SHORT','FLAT')` is constrained. The enum originates in
   an archived notebook (`notebooks/archive/00_project_setup.py:420`). The
   gold_trading_signals Delta table itself is "currently empty" with no DDL in
   `silver/`/`gold/`. → Failure scenario: an NL query or validator relies on the
   enum but nothing in the live schema enforces or defines it.

## Non-blocking notes

- **silver_sec_entities identity is described by three different tuples.**
  [table_semantics.yaml:79-84] keys `[accession_number, entity_type, entity_key,
  period_start, period_end, source_chunk_id]`; the MERGE key in
  `silver/06_silver_sec_entities.sql:122-126` is `(accession_number, entity_type,
  entity_key, entity_value, period_end)`; and the KG XbrlFact node key is
  `[accession_number, entity_key, entity_unit, period_start, period_end]`. All
  named columns exist, but the grain/identity contract and the idempotency key
  disagree (the SQL omits `source_chunk_id`/`period_start` and includes
  `entity_value`). Recommend aligning table_semantics keys to the actual MERGE
  key.
- **KG `CHUNK_SUPPORTS_FACT` edge is not buildable as specified.**
  [knowledge_graph.yaml:22] Chunk node is sourced from `silver_sec_sections`,
  which *excludes* `xbrl_fact_%` rows (`silver/05:38`), while XbrlFact's
  `source_chunk_id` is the bronze-level xbrl `record_key`
  (`silver/06:34`, `_record_key("xbrl", ...)` in
  `notebooks/02_ingest_sec_edgar.py`). No Chunk node corresponds to an XBRL fact's
  source chunk, so the edge has no joinable evidence. The xbrl→chunk relationship
  is a soft reference to a bronze chunk, not a silver section chunk.
- **Restatement supersession is still unmodelled.** KG `pit_rule` (line 3) says
  edges are visible when `information_available_ts <= as_of` and "edge availability
  is the max of its evidence/endpoint availability", but there is no
  valid-from/valid-to or superseded-by semantics, so an XBRL restatement appears
  as a second fact rather than superseding the prior one. Honest, but incomplete
  for XBRL facts.
- **External-contract test coverage is only partial.** `EXTERNAL_SCHEMA_CONTRACTS`
  (tests/test_ontology.py:14-19) guards `gold_regime_features` and
  `gold_tradable_universe` only. The 19 skips are legitimate (those tables have no
  defining SQL in `silver/`/`gold/`), but the following skipped tables are *not*
  covered by any contract and their keys are unverified:
  `bronze_ohlcv`, `bronze_ohlcv_day`, `bronze_options_day`, `bronze_fed_series`,
  `bronze_cftc_fut`, `bronze_cot`, `bronze_sec_filings`, `bronze_sec_filings_v2`,
  `silver_ohlcv_quarantine`, `gold_sec_features`, `gold_sec_chunk_embeddings`,
  `gold_trading_signals`. (I verified `gold_sec_features` keys
  `[ticker, accession_number]` and `gold_sec_chunk_embeddings` keys
  `[chunk_id, embedding_model]` against
  `gold/gold_sec_features.py` and `pipelines/build_sec_embeddings.py` respectively
  — both correct — but the test does not enforce them.)
- **gold/02 put_call_ratio case-sensitivity risk.** `gold/02:73-74` filters
  `right = 'PUT'`/`'CALL'`, but `notebooks/refresh_bronze_options.py::_shape_day`
  writes `right` as lowercase `'call'`/`'put'` (line 476-479). The ontology's
  `put_call_ratio` formula is stated correctly (put vol / call vol), but if the
  146M-row `bronze_options_day` carries lowercase `right`, the SQL computes 0/0.
  This is a gold-SQL bug, not an ontology error, but it means the metric may not
  actually be computable as described.
- `deterministic_counts: {node_types: 9, edge_types: 10}` (knowledge_graph.yaml:2)
  is self-consistent but easily misread as the full counts; the 3 LLM nodes /
  6 LLM edges are listed with `optional_llm_enrichment` markers.

## Mutation check of the new test (in /tmp, worktree untouched)

```
BASELINE:                    21 passed, 19 skipped
MUTATION A (phantom key, silver_ohlcv keys + phantom_key):
  FAILED test_table_keys_exist_in_sql_schema[silver_ohlcv]
  E   silver_ohlcv has no columns ['phantom_key']
MUTATION B (filter column, regular_session_only + phantom_flag):
  FAILED test_filter_columns_exist_in_sql_schema[regular_session_only]
  E   silver_ohlcv has no columns ['phantom_flag']
MUTATION C (join column, lineage key + phantom_join_col):
  FAILED test_join_columns_exist_in_sql_schema
  E   silver_ohlcv has no columns ['phantom_join_col']
```

Each of the three mutation classes is caught by the new test. The 19 skips are
legitimate (no DDL/transform in `silver/`/`gold/` on this branch), but only 2 of
the skipped gold tables are guarded by the external-contract test.

## Checks run

- `python3 -m pytest tests/test_ontology.py -q` → 21 passed, 19 skipped
- mutation A/B/C (above) → each fails the intended test
===VERDICT END===
