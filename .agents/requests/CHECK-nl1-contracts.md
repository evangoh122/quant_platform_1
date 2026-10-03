# CHECK: NL1 contracts and semantic registry (DeepSeek)

Branch `slice/nl-contracts`. Spec: `.agents/requests/BUILD-nl1-contracts.md` plus the amendment
`BUILD-nl1-amendment-put-call.md`. Plan: `docs/PUBLIC_NL_ANALYTICS_V1_PLAN.md`. MiMo built
`analytics_nl/` (contracts, registry, aliases, policy, schemas, data YAML) with 167 tests. Read-only.
Write `.agents/deepseek/VERDICT-nl1-contracts.md` (===VERDICT START/END===, Status).

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
