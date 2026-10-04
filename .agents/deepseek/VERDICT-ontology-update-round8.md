===VERDICT START===
# VERDICT: ontology-update-round8 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 8

Scope: `git diff 109fb5c..4030e2e` (`fix(ontology): round 8` vs its parent) on branch
`slice/ontology-update`. Read-only for source; all mutation copies under
`/tmp/ontology-update-round8-mut-{C,D,E}`. Lane-only code verified with `git show <branch>:<path>`
(`slice/rag-coverage`, `slice/rag-kg`, `slice/nl-contracts`).

## Verdict summary
All 7 review findings and the new item 8 are fixed with file:line evidence. The three
surviving review mutations (M-C, M-D, M-E) now fail. No test was deleted or weakened.
Test counts: 34 passed, 35 skipped (was 30 passed pre-round-8; +4 new guards). `git diff --check` clean.

## Findings (all non-blocking)

1. [metric_definitions.yaml:60] The precise figure "12 populated iv_atm values among 19,390
   current gold rows" is a live-observation count I cannot reproduce from code. The qualitative
   claim — IV is a single quote-snapshot date and effectively unavailable historically — is
   fully code-backed (gold/02_gold_options_features.sql header: "SINGLE-DAY snapshot
   (2026-09-02, 12 underlyings)"; `atm` CTE LEFT JOINs `bronze_options_quotes`, NULL for every
   other date). Not blocking; the note's substance is correct.
2. [slice/rag-coverage:pipelines/sec_rag_ingest.py:385] The dataclass type comment
   `CikMappingResult.status  # mapped | missing | ambiguous` still names `ambiguous`, which the
   writer never emits (build_cik_map assigns only `mapped` :359 / `missing` :368). The ontology
   is now correct; this is a residual comment on the rag-coverage lane, not this repo's
   `ontology/` file, so out of scope for round 8. Follow-up for that lane.
3. [ontology/knowledge_graph.yaml:32] SUPERSEDES condition states ordering "(accepted_ts,
   accession)" but build.py:520 sorts by `(accepted_ts, accession, node_id)`. The ontology's
   statement is accurate for the series identity; it omits only the node_id tie-breaker. Non-blocking.

## Item-by-item verification

1. `sec_cik_mapping_log` `ambiguous` dropped — DONE. table_semantics.yaml:73 `statuses: [mapped, missing]`;
   :67 status_note now "missing mappings are recorded" (was "missing or ambiguous"). Guarded by
   new snapshot tests/fixtures/sec_cik_mapping_log_status_snapshot.yaml + test
   tests/test_ontology.py:281-293. Writer verified: build_cik_map assigns only `mapped`/`missing`
   (slice/rag-coverage:pipelines/sec_rag_ingest.py:359, :368).
2. `gold_regime_features` removed as a model-features source — DONE. join_hints.yaml:66 and :83
   both drop it; gold/05_gold_model_features.sql joins exactly ohlcv/options/sec/cot (no regime CTE),
   and table_semantics.yaml:230 `source_pit_columns` lists the four real columns.
3. `point_in_time_universe` latest-snapshot-as-of — DONE. filters.yaml:3 now
   `u.trade_date = (SELECT MAX(snapshot.trade_date) ... WHERE snapshot.trade_date <= :as_of_date)`
   and :5 rule text matches. Columns {symbol, trade_date, information_available_ts} remain within the
   EXTERNAL_SCHEMA_CONTRACTS set, so the guard test still passes.
4. Lineage key lists — DONE. join_hints.yaml:24-25 add `cardinality: one_to_many` + grain note;
   :29 restores `event_ts -> feature_ts`; :34 restores `underlying -> symbol` + `event_date -> feature_ts`.
5. XbrlFact key vs SUPERSEDES identity — DONE. knowledge_graph.yaml:11 key now
   `[cik, accession_number, entity_key, period_start, period_end, entity_unit, entity_value, source_chunk_id]`
   (= sec_kg/model.py xbrl_fact_id, :183-196) plus `identity_note`; :32 states the series identity
   `(cik, concept, period_start, period_end, unit)` ordered by `(accepted_ts, accession)` (= build.py:507-508, :520).
6. Registry-default (unadjusted fallback) note added to `price` and `volume` — DONE.
   metric_definitions.yaml:8 and :22; default confirmed at slice/nl-contracts:analytics_nl/data/policy_bounds_v1.yaml:40
   (`adjusted_source_available: false`).
7. `exclude_bad_quotes` NULL-safe — DONE. filters.yaml:33 uses `COALESCE(is_locked,false)/COALESCE(is_crossed,false)`
   + note :35. Code confirmed: silver/03_silver_options_quotes.sql:41-43 sets the flags only when bid/ask present,
   and :7-8 records bid/ask absent across all 61,882 rows.
8. Mixed-case `right` + IV snapshot-only — DONE. table_semantics.yaml:29 `right_rule` (UPPER normalize);
   metric_definitions.yaml:66 put_call_ratio note (uppercase 2024-01..2026-09-04, lowercase 2026-09-08..2026-10-01);
   :60 implied_volatility note. Code confirmed: gold/02_gold_options_features.sql:76-77 compares `'PUT'/'CALL'` only;
   notebooks/refresh_bronze_options.py:206 emits lowercase `call`/`put`.

Corporate-actions section: untouched (verified in diff; table_semantics.yaml bronze_corporate_actions unchanged).

## Mutation proofs (re-run myself in /tmp copies; each full `cp -r` of worktree)

| id | mutation | expected | observed |
|----|----------|----------|----------|
| M-C | add term `tradable_universe` reusing `universe`'s aliases (business_terms.yaml) | fail | **FAILED** `test_business_term_aliases_have_one_owner` — "'tradable_universe' is owned by both 'universe' and 'tradable_universe'" |
| M-D | `deterministic_counts.node_types` 9 → 11 (knowledge_graph.yaml:2) | fail | **FAILED** `test_knowledge_graph_deterministic_counts_match_declared_types` — {node_types: 11} != {node_types: 9} |
| M-E | flip both PIT `<=` → `>=` (join_hints.yaml:67, :84) | fail | **FAILED** `test_join_availability_comparisons_do_not_look_ahead` — "uses a look-ahead comparison: ... >= target.prediction_ts" |

PIT-direction test iterates over the real join conditions: exactly 2 are exercised
(`latest_feature_asof_prediction.condition` and `model_feature_assembly.condition`, both `<=`); all
lineage `temporal_rule` entries use prose ("equals"/"cannot precede") with no comparison operator, so
they are correctly not asserted. Counted programmatically.

No test deleted/weakened: `git diff ... -- tests` shows only additions (+4 tests) and an equivalent
refactor of `test_no_duplicate_terms` (extracted `_normalize_business_term`); the
`test_join_columns_exist_in_sql_schema` change is strictly stricter (now checks mapped left/right keys).

## Checks run
- `python3 -m pytest tests/test_ontology.py -q -rs` → **34 passed, 35 skipped** (7.0s)
- `git diff --check 109fb5c 4030e2e` → clean
- `python3 -m pytest tests/test_ontology.py::test_business_term_aliases_have_one_owner -q` (mut-C) → 1 failed
- `python3 -m pytest tests/test_ontology.py::test_knowledge_graph_deterministic_counts_match_declared_types -q` (mut-D) → 1 failed
- `python3 -m pytest tests/test_ontology.py::test_join_availability_comparisons_do_not_look_ahead -q` (mut-E) → 1 failed
===VERDICT END===
