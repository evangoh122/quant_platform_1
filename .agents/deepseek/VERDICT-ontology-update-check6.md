# VERDICT: ontology round 6 (commit 64d5160)

Checker: Claude Sonnet subagent (DeepSeek out of credit)

===VERDICT START===
CHANGES_REQUESTED
===VERDICT END===

Scope: factual correctness vs code at current branch tips (slice/corporate-actions 76027ad, slice/nl-contracts f00cd8a,
slice/rag-coverage ab93003, slice/rag-kg f6c6ad4, origin/main). Test run: `python3 -m pytest tests/test_ontology.py -q -rs` -> 29 passed, 35 skipped.

## Findings (numbered)

1. BLOCKER (small, false today): ontology/table_semantics.yaml:65 `sec_ingest_log.statuses` lists `missing_cik`.
   The writer never emits it: only planned, in_progress, succeeded, failed, skipped_existing
   (slice/rag-coverage:pipelines/sec_rag_ingest.py:1078,1097,1113,1122-1174,1161). `missing_cik` appears only in the original request
   text (.agents/requests/BUILD-rag-coverage.md:52); unmapped CIKs go to sec_cik_mapping_log (status missing|ambiguous, sec_rag_ingest.py:381,1007-1021).
   Fix: drop `missing_cik` (or mark "spec-only, not emitted").
2. Corporate actions is STALE vs the current slice/corporate-actions tip (non-blocking per instruction, record as follow-up; see below).
   table_semantics.yaml:22-23 says `massive: planned` and "branch implements only yfinance". Tip has MassiveCorporateActionsSource
   (etl/corporate_actions.py:255, source="massive" at :325), VALID_SOURCES={"massive","yfinance"} (notebooks/refresh_bronze_corporate_actions.py:43,
   _make_adapter), precedence massive>yfinance, +-3 day suppression (silver/08_silver_ohlcv_day_adjusted.sql:139-173) and SPLIT_SOURCE_MISMATCH
   (sql:183-251,432). Ontology also omits SPLIT_SOURCE_MISMATCH from `classification_values` (:102) and its reasons from :103.
   The ontology statement is accurate only against the older commit Codex read; it is false against the tip, so it must change when the lane merges.
3. Minor (non-blocking): gold_sec_coverage grain (table_semantics.yaml:195) says rows are "per canonical ticker in the all-history tradable universe".
   gold/07_gold_sec_coverage.sql:51-62 FULL OUTER JOINs universe, filing_agg, chunk_agg, so tickers outside gold_tradable_universe that have bronze
   filings/chunks also get rows. Reword to "universe members plus any ticker with filings/chunks". Columns/keys otherwise correct (ticker, cik, n_filings, n_chunks, first_filed, last_filed, last_ingest_ts; accepted_ts min/max confirmed :20-21).
4. Minor (non-blocking): NL1 metric formulas for realized_volatility/drawdown/momentum (metric_definitions.yaml, adjusted path) omit that
   the proposed DDL filters `WHERE return_1d IS NOT NULL` BEFORE computing vol, drawdown and LAG(20) (docs/NL1_PROPOSED_SERVING_VIEWS.md:157-183),
   so a masked break removes the whole row from the drawdown peak and the 20-row lag window, not just from the volatility. Also the live registry
   (slice/nl-contracts semantic_registry_v1.yaml:22-90) still tags price.* `price_adjustment: unadjusted` and policy_bounds_v1.yaml:40 defaults
   `adjusted_source_available: false`; ontology `price`/`volume` (adjusted_primary_unadjusted_fallback, status proposed) is correct about the DDL but should say the default today is the fallback.

## Verified correct (item 1, per table)
- bronze_corporate_actions: keys (symbol, ex_date, source), cols symbol/ex_date/split_ratio/source/fetched_ts/information_available_ts, ratio = new/old,
  PIT 09:30 America/New_York on ex_date (etl/corporate_actions.py:23-36,69-83; refresh_...py:40-53).
- silver_ohlcv_day_adjusted: all 8 adjustment_columns exist (sql:56-81); key (symbol,event_date) MERGE :519; PIT 16:30 ET :507-510; return_1d NULL when masked :496-500;
  "divide prices, multiply volume by cumulative_split_ratio" :297-305; global/current-scale note :11-15.
- data_quality_breaks: key (symbol,event_date), processed_ts exists (:48), classification enum SPLIT_EXPLAINED/UNEXPLAINED_PENDING (+CONFIRMED via review), 3 reasons :380-384 (all true, incomplete per #2).
- sec_cik_mapping_log: cols ticker/lookup_symbol/cik/status/reason/mapped_ts/run_id (sec_rag_ingest.py:1290-1311); key (run_id,ticker) is the request's logical key, writer wired in main (:1338-1361); statuses mapped|missing|ambiguous OK.
- sec_ingest_log: key (run_id,ticker,accession_number,attempt), logged_ts exists (:1283-1287), dry-run only when --log-dry-run (:1068). Only `missing_cik` wrong (#1).
- gold_sec_kg_build_runs: all 9 manifest columns match DDL (build_sec_knowledge_graph.py:216-248); key run_id (uuid4) and run_ts PIT OK. KG enum snapshot matches rag-kg sec_kg/model.py:19-54 exactly (12 node types, 13 edge types identical).
- bronze_cftc_com: keys/release_ts match refresh_bronze_cot.py:55-65,184-218 (sibling of bronze_cftc_fut).
- bronze_ohlcv_day: unadjusted, key (symbol,event_ts,timespan), event_date/ingest_ts are real columns (origin/main docs/DATA_SCHEMAS.md:18-33).
- 5 serve_* views: names equal registry approved_views; columns/keys/grain/PIT match proposed DDL (serve_options_metrics_v1 key (symbol,feature_ts); relative_performance has `benchmark`; gold_options_features has information_available_ts, SQL :63-70). All marked status: proposed, "Not live".

## Item 3: 9 NL1 metrics
Names equal analytics_nl/contracts.py Metric enum (:43-55). Sources/grain/formulas match the proposed DDL
(vol 20-row STDDEV_SAMP*SQRT(252) :157-161; drawdown :173-181; momentum LAG 20 :191; rel_perf daily spread :299 - ontology correctly notes doc prose says cumulative;
iv_atm = max-open-interest quote, put_call_ratio uppercase PUT/CALL caveat per origin/main gold/02 :63-108). Return-type metrics reference silver_ohlcv_day_adjusted or are flagged unadjusted with reason (return_N, rolling_realized_volatility, momentum_N on raw silver_ohlcv via gold/01). OK apart from #4 nuance.

## Item 4: joins
join_hints bronze_ohlcv_day_to_silver_ohlcv_day_adjusted keys (symbol,event_date) exist in both; PIT rule 16:30 ET / ex_date contract correct; no future-leaking join (cumulative ratio uses ex_date > event_date, sql:275). Adjusted lineage correct.

## Item 5: skips and mutation proofs
Why 35 skip: `_assert_columns` (tests/test_ontology.py:159) does pytest.skip when a table has no DDL/defining SQL in THIS worktree. The new tables' code
lives only on other slice branches (corporate-actions, rag-coverage, rag-kg, nl-contracts) and origin/main notebooks, so 23 table-key skips + 6 filter/join skips are
by design (rule-only filters: cot_forward_fill, fed_latest_vintage_as_of). Consequence: column/key claims for ALL round-6 new tables are NOT machine-checked here (they are covered only by this manual review);
the NEW round-6 tests (test_nl1_*, test_proposed_*, test_price_return_*, test_every_local_sql_target_*) are not skipped and pass. Not a defect of the new tests, but follow-up: re-run after the lanes merge so skips turn into real column checks (and ensure they don't remain skipped silently).
Mutation proofs (copies under /tmp/onto6-mut-*, all FAIL as required):
- M1 metric source_table -> nonexistent table: test_every_referenced_table_has_semantics FAILED.
- M2 live metric (rsp_spy_ratio_zscore_252) sourced from proposed serve_daily_prices_v1: test_proposed_tables_cannot_source_live_metrics FAILED.
- M3 return_N declared `adjusted` without adjusted_source_table: test_price_return_metrics_are_adjusted_or_explicitly_unadjusted FAILED.
- M3b return_N with price_adjustment flag removed: same test FAILED.
- M4 phantom NodeType in enum snapshot: test_knowledge_graph_vocabulary_matches_canonical_sec_kg_enums FAILED.

## Item 6: tests not weakened
`git diff b5b5ea7..64d5160 -- tests`: +77/-1; the single removed line is the `_table_references` key-set, replaced by a strict superset adding `adjusted_source_table`. No deletions/skips added.

## Follow-ups once slice/corporate-actions (round 6) merges
- bronze_corporate_actions: `massive: implemented`; replace source_note with precedence massive > yfinance per (symbol, ex_date); yfinance row within +-3 calendar days of a massive row for the same symbol is suppressed as the same event (massive wins date and ratio); keep key (symbol, ex_date, source).
- data_quality_breaks: add SPLIT_SOURCE_MISMATCH (is_masked=FALSE; split_error holds ratio deviation >0.001 or NULL for single-source) to classification_values and reason `split_source_mismatch` (reason codes SPLIT_SOURCE_MISMATCH/SPLIT_SINGLE_SOURCE if round 6 renames them; tip today uses the one reason string for both mismatch and single-source cases - re-verify at merge).
- Business term corporate_action / README text: drop "yfinance-only".
- Re-run the 35 skipped checks after merge.

