===VERDICT START===
# VERDICT: nl1-contracts — DeepSeek (re-check, round 3)
**Status:** CHANGES_REQUESTED
**Round:** 3 (check2, HEAD afab815, branch `slice/nl-contracts`)

The four round-3 fixes are verified. Two new blocking findings remain, one of
which (DDL columns) directly contradicts the put_call_ratio amendment's explicit
`feature_ts` requirement.

## Round-3 fixes — verified with proofs

- **Explicit DDL columns / `SELECT *` guard**: `tests/analytics_nl/test_ddl.py:45-81`
  normalises each ```sql block (strip comments, collapse all whitespace incl.
  newlines) before matching `\bSELECT\s+\*` and `\.\*`. Mutation proof (disposable
  copy under `/tmp/nl1-mutate`): inserting a newline-split `SELECT` / `*` and a
  `deduped.*` token each make `TestDDLNoSelectStar::test_no_select_star` FAIL
  (`AssertionError: SELECT * found…` / `table.* found…`). The old OR-of-negations
  test is gone.
- **2 Silver registry entries**: `price.trend` and `volume.trend` are `layer:
  silver` on `serve_bounded_daily_bars_v1` (`analytics_nl/data/semantic_registry_v1.yaml:19,192`).
  Mutation proof: rewriting the first Silver `serving_view` to
  `serve_bounded_daily_bars_v1_evil` makes `load_registry()` raise
  `RegistryValidationError` and the entire `test_registry.py` module ERRORs
  (fail-closed).
- **Silver boundary tests**: `TestSilverBounds` (test_policy.py:285-450) covers
  exactly-at and one-over for 2 years, 10 tickers, 10,000 rows, plus missing-scope
  and `volume.trend`; each just-over case REJECTs and `test_silver_reject_exposes_no_sql`
  asserts no SQL field. All pass (see Checks run).
- **Policy/schema sensitivity**: mutating `policy_bounds_v1.yaml` gold
  `date_bound_years 10→11` fails `test_gold_bounds`; mutating a model bound
  (`le=10_000→9999`) fails `TestSchemaSync`. Both proof mutations fail their
  target tests.

## Blocking findings

1. **[docs/NL1_PROPOSED_SERVING_VIEWS.md:42,47,49,65,193,208,224,230,232,248] Proposed
   DDL references columns that do not exist in the physical sources.**
   Cross-checked against `docs/DATA_SCHEMAS.md` (the authoritative schema doc) and the
   transform DDL:
   - `serve_options_metrics_v1` selects `trade_date` from `gold_options_features`
     (docs:193,208). `gold_options_features` has no `trade_date`; its grain column is
     `feature_ts` (timestamp) — `docs/DATA_SCHEMAS.md:385-401` and
     `gold/02_gold_options_features.sql:185`. The put_call_ratio amendment explicitly
     required `feature_ts`; the checked-in DDL uses `trade_date` instead.
   - `serve_daily_prices_v1` and `serve_bounded_daily_bars_v1` select `trade_date`,
     `adj_close`, and `information_available_ts` from `bronze_ohlcv_day`
     (docs:42,47,49,65 and :224,230,232,248). `bronze_ohlcv_day` has none of these:
     its columns are `event_date` (not `trade_date`), `close` (there is **no**
     `adj_close` anywhere in `docs/DATA_SCHEMAS.md` — grep returns zero matches), and
     `ingest_ts` (no `information_available_ts`) — `docs/DATA_SCHEMAS.md:18-33`.
     `information_available_ts` only exists as a gold/minute-level derived concept
     (`gold/05_gold_model_features.sql:15`), not on the daily bronze table.
   - Consequence: the registry's fixed `input_columns` (`adj_close` for
     price.trend/compare/rank/aggregate at `semantic_registry_v1.yaml:22,43,65,87`,
     and the derived `return_1d`, `realized_vol_20d`, `drawdown`, `momentum_20d`,
     `rel_perf`) are not backed by any real source, and the whole
     `serve_daily_prices_v1 → serve_daily_equity_metrics_v1 →
     serve_relative_performance_v1` chain is rooted in a fabricated `adj_close`.
     Concrete failure: NL2's deterministic compiler will emit SQL over the
     registry `input_columns`, producing `SELECT adj_close … FROM …bronze_ohlcv_day`
     (and `feature_ts`-vs-`trade_date` mismatch on options) that fails at execution.
     Fix: rename to the real grain columns (`event_date`/`feature_ts`), drop or
     explicitly source `adj_close` (or document that adjustment is not yet available
     and use `close`), and use a real PIT column or derive `information_available_ts`
     in the view.

2. **[analytics_nl/contracts.py:313-325] `DateExpression.relative` is a free-form
   string with no hostile-content validation, so the LLM output contract can express
   SQL.** `relative: str` (max 50) has no field validator (contrast
   `LLMEntityMention.text`, which rejects control chars, SQL/comment metacharacters,
   and prompt-injection). Proven:
   `DateExpression(relative="last month'; DROP TABLE gold_options_features; --")`
   and `LLMIntentOutput(..., date_expression={"relative": "2024'; SELECT 1 --"})`
   both validate successfully. `extra="forbid"` does not help because `relative` is a
   declared field. This violates CHECK item 1 ("the LLM output schema cannot express
   SQL … try to smuggle SQL through … dates"). Mitigation today is only that
   `resolve_relative_date` exact-matches `{last month, ytd}` and returns `None` for
   anything else — but the contract is the advertised trust boundary and should fail
   closed at validation. Fix: constrain `relative` to the closed set
   (`last month` / `YTD`, case-insensitive, normalized) or add the same
   control-char/SQL-metachar rejection as `LLMEntityMention.text`.

## Non-blocking notes

- [docs/NL1_PROPOSED_SERVING_VIEWS.md:168,175] `serve_relative_performance_v1`
  hardcodes `WHERE symbol = 'SPY'` and `'SPY' AS benchmark`, while the registry
  declares `benchmark` enum `[SPY, QQQ, RSP]` (`semantic_registry_v1.yaml` relative-
  performance entries). The doc discloses this ("defaults to SPY; parameterized
  queries should substitute"), so it is proposal-only, but NL2 must reconcile the
  fixed-view vs. three-benchmark gap.
- [analytics_nl/policy.py:136-137,198-203] `ENTITY_NOT_ALLOWED` and
  `MISSING_REQUIRED_SLOT` reason codes are effectively unreachable: there is no
  per-entry allowed-entity-kind data, and `CanonicalIntent.entities` has
  `min_length=1` / `date_range` is required, so a `sector` entity for a ticker-only
  metric is not rejected by policy (entity-kind validation is deferred to a later
  lane per BUILD §1.2, but the codes imply it happens here).
- [analytics_nl/aliases.py:188-215] `load_ticker_symbols` still catches only
  `FileNotFoundError`/`TypeError`; `importlib.resources.files("config")` raises
  `ModuleNotFoundError` when `config` is not packaged with an installed
  `analytics_nl` wheel (carried over from round 1, unchanged).
- [analytics_nl/registry.py:83-93,134-239] Parameter `default` is still not checked
  against `min`/`max`/`enum`, and `allowed_grouping`/`required_slots`/`aggregation`
  are only regex-checked, not validated against the closed enums/token sets
  (carried over from round 1, robustness-only; shipped data is correct).

## Checks run

- `python3 -m pytest -q tests/analytics_nl` → **175 passed** (0 failures)
- `python3 -m analytics_nl.export_schemas --check` → **All schemas match** (exit 0)
- `python3 -m pytest -q --ignore=tests/lakebase` → **713 passed, 67 skipped** (0 failures)
- Mutation proof (disposable `/tmp/nl1-mutate`): `SELECT *` guard, `table.*` guard,
  Silver view-rename (registry fail-closed), policy bound, and schema-sync mutations
  each fail their target test, then the copy is discarded.
- Cross-check: `grep adj_close docs/DATA_SCHEMAS.md` → 0 matches; `grep trade_date`
  → 0 matches; `bronze_ohlcv_day` has `event_date`/`close`/`ingest_ts` only;
  `gold_options_features` has `feature_ts` (not `trade_date`).
- Independent probe: `DateExpression(relative="…DROP TABLE…")` and
  `LLMIntentOutput(date_expression={"relative":"…SELECT 1 --"})` both validate
  (blocking finding 2).
===VERDICT END===
