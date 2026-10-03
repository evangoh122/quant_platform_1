# CHECK: ontology update (DeepSeek)

At the owner's request, Codex updated `ontology/` directly (commit "feat(ontology): align with live
tables..."). Read-only. Write `.agents/deepseek/VERDICT-ontology-update-check2.md` (===VERDICT START/END===,
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
