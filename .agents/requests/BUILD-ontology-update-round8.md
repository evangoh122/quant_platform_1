# BUILD ontology round 8 (author: Codex gpt-5.6-sol) — fixes from dataexpert Claude review 1

Edit files only (you cannot commit or write .agents/). Print a report between ===REPORT START=== and ===REPORT END===.
Review: .agents/reviewer/VERDICT-ontology-update-review1.md (CHANGES_REQUESTED). Fix ALL 7 findings and close the 3 test gaps:

1 (blocker). sec_cik_mapping_log `statuses: [mapped, missing, ambiguous]` (table_semantics.yaml:72, :66): `ambiguous` is never
  emitted (slice/rag-coverage:pipelines/sec_rag_ingest.py build_cik_map assigns only mapped/missing). Drop it (round-6 precedent);
  add a status-snapshot test like the sec_ingest_log one, citing branch:path:line.
2. join_hints.yaml:63-64 and :80-81 list gold_regime_features as a gold_model_features source; gold/05_gold_model_features.sql joins
  only ohlcv/options/sec/cot and nothing produces gold_regime_features. Remove it from both (or mark planned_source: true and make
  tests exclude planned sources from PIT resolution — prefer removal).
3. filters.yaml point_in_time_universe: SQL ("ever a member on/before as_of_date") contradicts the rule text ("latest eligible
  snapshot"). Make it the latest-snapshot-as-of-date predicate (trade_date = max trade_date <= as_of_date), which is what PIT
  universe membership means here; update the rule text to match exactly.
4. Lineage key lists: :23 bronze_sec_filings_v2 -> silver_sec_entities is one-to-many (say so / grain); :27 restore the
  event_ts -> feature_ts mapping in keys; :32 add event_date to bronze_options_day -> gold_options_features keys.
5. knowledge_graph.yaml XbrlFact key vs SUPERSEDES identity: align with slice/rag-kg:sec_kg/model.py:210-224 and state that the
  supersede series identity is (cik, concept, period_start, period_end, unit) ordered by (accepted_ts, accession)
  (sec_kg/build.py:505-510) — node identity != supersede-series identity.
6. Add the registry-default (unadjusted fallback) note to `price` and `volume` too.
7. exclude_bad_quotes: is_locked/is_crossed are always NULL (bid/ask absent, silver/03_silver_options_quotes.sql:7-8,41-43);
  use COALESCE(..., false) semantics in the filter SQL and add a note.
8. ALSO (new, found by Claude live 2026-10-04): put_call_ratio — bronze_options_day.`right` is mixed case: uppercase
  PUT/CALL 2024-01..2026-09-04, lowercase put/call 2026-09-08..2026-10-01. gold/02 compares uppercase only, so recent rows
  are miscounted, and gold_options_features currently ends at 2026-09-04. A separate MiMo lane is fixing the SQL; in the
  ontology, document `right` as case-insensitive (normalize with UPPER) in table_semantics for bronze_options_day and the
  put_call_ratio caveat. And implied_volatility: iv_atm is populated for 12 of 19,390 gold rows (quotes snapshot only, by
  design) — the implied_volatility metric must state data availability is a single snapshot date and is effectively
  unavailable historically.
Tests to add (the review's surviving mutations must now fail):
  M-C duplicate/conflicting aliases across business terms → test fails;
  M-D deterministic_counts must equal the actual counts of deterministic node/edge types → test fails if they differ;
  M-E every join `condition`/`temporal_rule` that compares availability must use `<=`/`<` against the as-of side (assert no
      `>=`/`>` look-ahead patterns) → flipping to `>=` fails.
Run python3 -m pytest tests/test_ontology.py -q and report counts. Do NOT touch the corporate-actions section.
