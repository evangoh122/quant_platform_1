# CHECK: NL1 contracts and semantic registry (DeepSeek)

Branch `slice/nl-contracts`. Spec: `.agents/requests/BUILD-nl1-contracts.md` plus the amendment
`BUILD-nl1-amendment-put-call.md`. Plan: `docs/PUBLIC_NL_ANALYTICS_V1_PLAN.md`. MiMo built
`analytics_nl/` (contracts, registry, aliases, policy, schemas, data YAML) with 167 tests. Read-only.
Write `.agents/deepseek/VERDICT-nl1-contracts-check3.md` (===VERDICT START/END===, Status).

Check, adversarially:
1. **The LLM output schema cannot express SQL, table or column names, code, or URLs.**
   `extra=forbid` everywhere, and enum-only metrics and operations. Try to smuggle SQL through every
   string field: entities, dates, labels.
2. **Registry identifiers** all match `^[a-z_][a-z0-9_]*$` and are on the approved-view list; there
   is no free-form identifier path. The 9 metrics are present, with `put_call_ratio` aggregated by
   MEAN, and a sum is rejected or disclosed.
3. **Policy bounds** exactly per the plan:
   - Gold: 10 years, 5,000 rows;
   - Silver: 2 years, 10 tickers, 10,000 rows;
   - intraday is rejected;
   - REJECT emits no SQL.

   Test the edge values (exactly at, just over).
4. **Aliases** are deterministic and traceable. Relative dates use an injected clock in
   America/New_York (DST edges). Check ambiguous names (GOOG vs GOOGL) and unknown entities.
5. **Schema sync:** the checked-in JSON schemas equal the models (mutate a model → the sync test
   fails).
6. **The proposed serving-view DDL** (`docs/NL1_PROPOSED_SERVING_VIEWS.md`) is point-in-time safe
   (filters on `information_available_ts`) and references real columns (cross-check
   `gold_options_features`, `bronze_ohlcv_day`).
7. The tests fail on the pre-change code.

Run `python3 -m pytest -q tests/analytics_nl`, and the full suite with `--ignore=tests/lakebase`.

## Re-check after round 3 (this run)
MiMo round 3 addresses your 4 findings:
- explicit DDL columns;
- a whitespace/newline-insensitive `SELECT *` and `table.*` guard;
- 2 Silver registry entries;
- Silver boundary tests (exactly at / one over, for 2 years, 10 tickers and 10,000 rows, plus
  missing scope).

175 tests pass. Verify each finding with proofs:
- the new guard FAILS on the round-2 DDL (mutation);
- the Silver entries are real and served by a bounded, PIT-filtered view with explicit columns;
- each just-over case REJECTs with no SQL.

Write `.agents/deepseek/VERDICT-nl1-contracts-check2.md`.

## Re-check after rounds 4–5 (this run)
Your check2 found phantom DDL columns. Round 4 switched to the REAL columns (`bronze_ohlcv_day` has
NO `trade_date`/`adj_close`/`information_available_ts`; options use `feature_ts`), derived daily PIT
(16:30 New York), split-safety rejection, and a schema-truth test. Round 5 removed a misleading
`close AS adj_close` alias, and roots the daily metrics on `silver_ohlcv_day_adjusted`. That table
comes from the corporate-actions lane `slice/corporate-actions`; read its columns from
`git show origin/slice/corporate-actions:silver/08_silver_ohlcv_day_adjusted.sql`. It's flagged
pending, with the split-safety rejection as the fallback.

Verify:
- every DDL/registry column exists in `source_schemas_v1.yaml`, and those schemas match live/source
  DDL (including the corp-actions SQL);
- the schema-truth test fails on a reintroduced phantom column;
- the split fallback logic and data-quality-break disclosure are tested in both modes;
- the round-1 checks still hold.

Write `.agents/deepseek/VERDICT-nl1-contracts-check3.md`.
