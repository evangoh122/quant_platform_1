# CHECK: ontology update (DeepSeek)

At the owner's request, Codex updated `ontology/` directly (commit "feat(ontology): align with live
tables..."). Read-only. Write `.agents/deepseek/VERDICT-ontology-update-check5.md` (===VERDICT START/END===,
Status). Your job is FACTUAL CORRECTNESS against the code: the ontology will drive the NL-analytics
semantic registry and the knowledge graph, so an error here propagates.

Check:
1. **`table_semantics.yaml`:** for every table, verify grain, keys, PIT column and freshness against
   the SQL and code that build it (`silver/*.sql`, `gold/*`, `pipelines/run_silver_gold.py`,
   `notebooks/refresh_bronze_*.py`, `docs/DATA_SCHEMAS.md`). Flag any column or key that doesn't
   exist.
2. **`metric_definitions.yaml`:** each formula must match the IMPLEMENTATION:
   - `med_adv_60d` (`gold/06`): a full 60-session window, lagged;
   - breadth regime (`gold/07`): SMA50 / z252 guards;
   - realized vol, drawdown, momentum, returns;
   - `iv_atm`, `put_call_ratio`;
   - COT crowding (gold COT code);
   - the residual s-score: lagged window, cumulative residual over L / sigma;
   - deflated Sharpe (`ml/` or the strategy code).

   Note: some of this code is on branches not yet on main (`strategies/` is #16), so judge against
   `docs/QUANT_STRATEGIES.md` and anything visible.
3. **`join_hints.yaml`:** every join must be point-in-time safe, as-of on `information_available_ts`,
   with no look-ahead. Check ticker↔cik and chunk↔entity.
4. **`knowledge_graph.yaml`:** 12 node types and 16 edges. Is each edge's PIT semantics (valid-from
   `accepted_ts`, restatement supersession) coherent? Is anything missing for XBRL facts?
5. **`filters.yaml` / `business_terms.yaml`:** no duplicate or conflicting terms, and aliases are
   correct (e.g. GOOG vs GOOGL).
6. `tests/test_ontology.py` actually catches a reference to a non-existent table, and a duplicate
   term (prove it by mutation in /tmp).

## Re-check after Codex round 2 (this run)
Codex fixed your 7 findings and extended `tests/test_ontology.py` to parse SQL schemas. Re-verify
each finding against the code. The test has 19 skips, because `gold/06`/`gold/07` live on the #16
branch, not main. Are those skips legitimate, and does the external-contract test cover them?

Mutation-check the new test: a phantom key, a filter column or a join column must each fail it.
Hunt for any remaining factual error. Write `.agents/deepseek/VERDICT-ontology-update-check2.md`.

## Re-check after Codex round 3 (this run)
Codex fixed the `bronze_fed_series` vintage grain and the other check2 findings (commit "fix(ontology):
round 3"). Re-verify every finding against the code. FYI: the KG lane (`slice/rag-kg`) wants to add
`gold_sec_kg_nodes` and `gold_sec_kg_edges` (see `.agents/requests/kg_ontology_additions.diff`).
Check whether those entries are accurate against `sec_kg/` on that branch
(`git show origin/slice/rag-kg:sec_kg/model.py`), so Codex can add them next.

Write `.agents/deepseek/VERDICT-ontology-update-check3.md`.

## Re-check after Codex round 4 (this run)
Codex fixed:
- the bronze_ohlcv_day / bronze_options_day keys;
- added the KG table semantics;
- corrected the KG join hints (`chunk_id` vs `source_chunk_id`);
- the test now parses the notebook key constants. Mutation: `event_date` as a bronze key → 2 fail.

Re-verify each of your check3 findings, and do a FINAL full pass. If nothing blocking remains, say
APPROVED. Write `.agents/deepseek/VERDICT-ontology-update-check4.md`.

## Re-check after Codex round 5 (this run)
Codex's own review found that the KG edge names didn't match the canonical
`origin/slice/rag-kg:sec_kg/model.py` enums. Round 5 aligns the node and edge names, adds
`SOURCED_FROM`/`SUPERSEDES` and the filing-level citation semantics, and adds an enum-sync test with
a snapshot fixture. Verify that the names equal the enums exactly, that the snapshot matches
model.py, and that the mutation test works. Write `.agents/deepseek/VERDICT-ontology-update-check5.md`.
