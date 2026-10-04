===VERDICT START===
# VERDICT: ontology-update — DeepSeek (Schema & API Contract lane)

**Status:** CHANGES_REQUESTED
**Round:** 1
**Branch:** `slice/ontology-update` (`06d63fb`)

Checker verdict: read-only. I did not modify the worktree. Scratch mutation
proofs ran under `/tmp/onto_mutate`. The ontology is largely well-constructed
(grain/keys/PIT columns and the PIT rules are the strongest part), but it
contains several concrete factual errors against the code that will propagate
into the NL-analytics semantic registry and the knowledge graph.

## Blocking findings

1. **join_hints.yaml lineage names the wrong source tables (3 of 9 lineage edges).**
   - [join_hints.yaml:6-9] `bronze_cot_to_silver_cot_positions` sets
     `left_table: bronze_cot`, but `silver_cot_positions` is built from
     `bronze_cftc_fut` (`silver/07_silver_cot_positions.sql:77`). `bronze_cot`
     is 0 rows and is explicitly not the source (`silver/07...sql:3`).
   - [join_hints.yaml:10-13] `bronze_sec_filings_to_silver_sec_sections` sets
     `left_table: bronze_sec_filings`; the transform reads
     `bronze_sec_filings_v2` (`silver/05_silver_sec_sections.sql:34`).
   - [join_hints.yaml:14-17] `bronze_sec_filings_to_silver_sec_entities` — same
     error, `bronze_sec_filings_v2` (`silver/06_silver_sec_entities.sql:36,64,88,116`).
   → Failure scenario: an NL "lineage" query reports `bronze_cot`/`bronze_sec_filings`
   as upstream of the silver tables, pointing analytics at empty/wrong sources.

2. **table_semantics.yaml keys reference columns that do not exist.**
   - [table_semantics.yaml:96-100] `gold_regime_features` keys `[session_date]`;
     the real column is `trade_date` (`gold/07_gold_regime_features.sql` `CREATE
     TABLE` — `trade_date DATE NOT NULL`). `session_date` is not a column.
   - [table_semantics.yaml:101-105] `gold_tradable_universe` keys
     `[symbol, as_of_date]` and grain "as_of_date"; the real column is
     `trade_date` (`gold/06_gold_tradable_universe.sql`). `as_of_date` does not
     exist.

3. **filters.yaml reuses the same phantom column.** [filters.yaml:3]
   `point_in_time_universe` predicates on `u.as_of_date <= :as_of_date`, but
   `gold_tradable_universe` has `trade_date`, not `as_of_date`. The generated
   filter SQL will fail to parse against the live table.

4. **iv_atm formula contradicts the implementation.** [metric_definitions.yaml:28]
   says `iv_atm` "selects minimum ABS(strike / underlying_price - 1)".
   The code selects by **maximum open interest**, not ATM-by-moneyness:
   `gold/02_gold_options_features.sql:102-109` `ROW_NUMBER() ... ORDER BY
   open_interest DESC NULLS LAST, strike`. Also `underlying_price` is not a
   column anywhere in `bronze_options_quotes` (only `last_price`). The semantic
   registry would describe a different metric than is computed.

5. **s_score denominator window is mis-stated.** [metric_definitions.yaml:41]
   writes `STDDEV_SAMP(epsilon[i,t-L:t])` — the residual std over the *lookback*
   window `L`. The implementation divides the `L`-window cumulative residual by
   the **60-day estimation-window** sigma, not `L`:
   `strategies/residual_reversion.py` `compute_residuals` sets
   `sigma = _trailing_std(residual, window=60)` then `s_score = s_cum/sigma`
   where `s_cum = residual.rolling(lookback=5).sum()`.

6. **Metric `source_table` fields point at tables that do not hold the metric.**
   - [metric_definitions.yaml:11-12] `drawdown` → `gold_trading_signals` has no
     equity/return column; drawdown is computed in `ml/evaluate.py:167-169`.
   - [metric_definitions.yaml:44-46] `deflated_sharpe_ratio` →
     `gold_trading_signals`; computed in `ml/evaluate.py:95-116`
     (`deflated_sharpe_ratio`). (Formula itself matches the implementation.)
   - [metric_definitions.yaml:37-42] `residual` and `s_score` →
     `gold_model_features` has no `epsilon`/residual column; computed in
     `strategies/residual_reversion.py` from daily returns.

7. **knowledge_graph.yaml defines node types with no backing entity_type.**
   [knowledge_graph.yaml:13-15] `Segment`, `Product`, `Customer` are declared as
   node types sourced from `silver_sec_entities`, but that table only emits
   `xbrl_fact`, `company`, `event`, `risk_factor`
   (`silver/06_silver_sec_entities.sql`, four `UNION ALL` arms). The three node
   types — and their five edges (`COMPANY_HAS_SEGMENT`, `COMPANY_OFFERS_PRODUCT`,
   `COMPANY_HAS_CUSTOMER`, `SEGMENT_REPORTS_FACT`, `PRODUCT_REPORTS_FACT`) — are
   unsupported by current data, so the graph over-claims 12 node types / 16
   edges.

## Non-blocking notes

- [metric_definitions.yaml:4,16] `return_20d`, `momentum_20d`,
  `momentum_12m_ex_1m` are listed as variants of `gold_ohlcv_features`, but that
  table is minute-grain and only carries `return_1m/5m/15m/30m` and
  `momentum_5m/15m`. The 20d/12m variants need daily data and are not in the
  source table.
- [metric_definitions.yaml:24-26] `breadth_regime` matches `gold/07` (SMA50 +
  20d slope), but the ontology omits `rsp_spy_ratio_zscore_252`, which exists as
  a column in `gold/07_gold_regime_features.sql` — the "z252" the check names is
  a stored feature, not documented in the metric registry.
- [metric_definitions.yaml:13] `drawdown` note says max drawdown is the
  "absolute value of the minimum", but `ml/evaluate.py:169` returns the negative
  minimum (not absolute) — convention mismatch to resolve.
- [table_semantics.yaml:59-68] `silver_options_quotes`/`silver_options_trades`
  keys include `sequence_id`, which is hashed into `dedup_hash`
  (`silver/03...sql:45-46`, `04...sql:33-34`) but is not a stored column
  (absent from `docs/DATA_SCHEMAS.md`).
- [business_terms.yaml:5] the alias example `GOOGLE: GOOGL` uses a non-ticker
  ("GOOGLE") and never documents that `GOOG` (Class C) and `GOOGL` (Class A) are
  distinct securities — exactly the alias hazard the check calls out
  (`config/tickers.yaml:8755-8756` lists both).
- [knowledge_graph.yaml:8] `XbrlFact` node key omits `entity_unit`; two facts
  with the same concept/period but different units collapse. No `Unit` node type.
- [knowledge_graph.yaml:2,17-32] every edge carries only `pit: accepted_ts`;
  there is no valid-from / superseded-by (restatement) semantics, so XBRL
  restatements cannot be modelled coherently.
- [join_hints.yaml:50-55] `ticker_to_cik` lists only `ticker` keys with no
  as-of/temporal guard, even though ticker→issuer mappings are time-varying.
- `docs/DATA_SCHEMAS.md` is missing five tables the ontology registers
  (`bronze_fed_series`, `silver_ohlcv_quarantine`, `gold_regime_features`,
  `gold_tradable_universe`, `gold_sec_chunk_embeddings`); the ontology itself is
  internally consistent (the referenced tables/columns exist in notebooks /
  pipelines), but the schema doc is stale.

## Checks run

```
$ python3 -m pytest tests/test_ontology.py -q
3 passed in 0.36s
```

Mutation proof (in `/tmp/onto_mutate`, worktree untouched):

```
$ python3 /tmp/onto_mutate/mutate.py
baseline:           3 passed
mutation A: bogus source_table 'nonexistent_table' ->
  FAILED tests/test_ontology.py::test_every_referenced_table_has_semantics
  E   AssertionError: Missing table semantics: ['nonexistent_table']
```

```
$ python3 /tmp/onto_mutate/mutate_b.py
mutation B: duplicate term 'information available_ts' ->
  FAILED tests/test_ontology.py::test_no_duplicate_terms
  E   AssertionError: assert 18 == 17
```

Both mutations are caught: the test suite does detect a reference to a
non-existent table and a duplicate (normalized) term.
===VERDICT END===
