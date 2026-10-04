===VERDICT START===
# VERDICT: nl1-contracts — DeepSeek (re-check, rounds 4–5)
**Status:** CHANGES_REQUESTED
**Round:** 5 (check3, HEAD 24d5907, branch `slice/nl-contracts`)

Round 4–5 delivered exactly what they claimed: the phantom `trade_date`/`adj_close`/
`information_available_ts`-on-bronze defects are gone, `silver_ohlcv_day_adjusted`
columns match the corporate-actions lane DDL verbatim, and the split-safety fallback
is tested in both modes. One blocking defect from check2 remains unfixed, and one
check3 criterion (data-quality-break disclosure) is only documented, not tested.

## Round 4–5 fixes — verified with proofs

- **Source schemas match live DDL (incl. corp-actions SQL).**
  - `bronze_ohlcv_day` (15 cols) == `docs/DATA_SCHEMAS.md:18-33` (`event_date`,
    `close`, `ingest_ts`; **no** `trade_date`/`adj_close`/`information_available_ts`).
  - `gold_options_features` (16 cols) == `docs/DATA_SCHEMAS.md:385-401` (`feature_ts`,
    `iv_atm`, `put_call_ratio`; **no** `trade_date`).
  - `silver_ohlcv_day_adjusted` (23 cols) == `git show origin/slice/corporate-actions:silver/08_silver_ohlcv_day_adjusted.sql`
    — column-for-column identical (incl. `adj_close`, `return_1d`, `is_data_quality_break`,
    `information_available_ts`, `processed_ts`), and correctly flagged
    `status: pending_corporate_actions_lane` in `source_schemas_v1.yaml:26-52`.
  - `serve_options_metrics_v1` DDL uses `feature_ts` (not `trade_date`); daily views
    use `event_date` and derive `information_available_ts` as 16:30 America/New_York.
- **Schema-truth test fails on a reintroduced phantom column (mutation proof).**
  In a disposable copy (`/tmp/nl1-mut`) I rewrote `price.trend` `input_columns` to
  `[symbol, trade_date, close]` and ran
  `TestSourceSchemaColumns::test_registry_columns_exist_in_source` → **FAILED**
  (`input_column 'trade_date' not found … Available: [event_date, close, adj_close, …]`).
  The phantom-column guard is real, not vacuous.
- **Split fallback logic tested in both modes.** `TestAdjustedSourceFallback`
  (`test_policy.py:670-786`) proves `adjusted_source_available=True` skips
  `UNADJUSTED_CORPORATE_ACTION` and `False` rejects it; `TestCorporateActionRejection`
  (`test_policy.py:523-667`) covers all five unadjusted-price metrics, empty
  `known_splits`, and out-of-window/symbol misses. Default flag is asserted `False`.
- **`close AS adj_close` alias removed.** `test_close_used_not_adj_close_source`
  (`test_ddl.py:127-136`) and `test_mutation_reintroduce_adj_close_alias_fails`
  (`test_source_schema.py:205-214`) assert the string is absent from the DDL; the DDL
  is clean (grep confirms zero occurrences).

## Blocking findings

1. **[analytics_nl/contracts.py:318] `DateExpression.relative` is a free-form string
   with no hostile-content validation, so the LLM output contract still expresses SQL
   through the "dates" vector — carried from check2 finding #2, unresolved.**
   `relative: Annotated[str, Field(min_length=1, max_length=50)] | None` has no
   field validator (contrast `LLMEntityMention.text` at `contracts.py:302-311`).
   Proven against HEAD:
   - `DateExpression(relative="last month'; DROP TABLE gold_options_features; --")`
     → validates successfully.
   - `LLMIntentOutput(date_expression={"relative": "2024'; SELECT 1 --"}, …)`
     → validates successfully.
   `extra="forbid"` cannot help because `relative` is a declared field. The only
   mitigation today is `resolve_relative_date` (`aliases.py:218-255`) exact-matching
   `{last month, ytd}` and returning `None` otherwise — but the contract is the
   advertised trust boundary and this directly violates round-1 CHECK item 1
   ("smuggle SQL through every string field: entities, dates, labels"). There is no
   test asserting `relative` rejects hostile content (`TestLLMIntentOutput` only
   exercises `entity_mentions`). **Fix:** constrain `relative` to the closed set
   `{last month, YTD}` (or add the same control-char/SQL-metachar rejection as
   `LLMEntityMention.text`). Until then the LLM-output schema is not fail-closed.

## Non-blocking notes

- **[check3 criterion "data-quality-break disclosure tested in both modes"]** is only
  *partially* met. The disclosure is documented in DDL prose
  (`docs/NL1_PROPOSED_SERVING_VIEWS.md:13-14,121,163,269`) and the column is asserted
  (`test_source_schema.py:168-182` includes `is_data_quality_break`), but there is no
  behavioral test of NULL-`return_1d` exclusion in adjusted vs. fallback mode. MiMo's
  own verdict acknowledges "documented but not testable against a live table until the
  lane merges." Acceptable for now only because the adjusted source does not exist yet;
  a prose-assertion test (that the DDL discloses the break-exclusion) would close this.
- [docs/NL1_PROPOSED_SERVING_VIEWS.md:280-306] `serve_relative_performance_v1` still
  hardcodes `WHERE symbol = 'SPY'` while the registry declares `benchmark ∈ {SPY,QQQ,RSP}`
  (carried from check2; disclosed in prose, NL2 must reconcile).
- [analytics_nl/policy.py:239-243] `MISSING_REQUIRED_SLOT` / `ENTITY_NOT_ALLOWED`
  remain unreachable given `CanonicalIntent` `min_length=1` entities and no per-entry
  allowed-entity-kind data (carried; robustness-only).
- [analytics_nl/aliases.py:188-215] `load_ticker_symbols` still catches only
  `FileNotFoundError`/`TypeError`, not `ModuleNotFoundError` for an unpackaged
  `config` (carried; installed-wheel edge case).
- [analytics_nl/registry.py:83-93] parameter `default` is still not checked against
  `min`/`max`/`enum` (carried; shipped data is correct).

## Checks run

- `python3 -m pytest -q tests/analytics_nl` → **223 passed** (0 failures)
- `python3 -m analytics_nl.export_schemas --check` → **All schemas match** (exit 0)
- `python3 -m pytest -q --ignore=tests/lakebase` → **761 passed, 67 skipped** (0 failures)
- Mutation (disposable `/tmp/nl1-mut`): `trade_date` phantom column →
  `test_registry_columns_exist_in_source` FAILS (`AssertionError: … 'trade_date' not found`).
- Independent probe (HEAD): `DateExpression(relative="…DROP TABLE…")` and
  `LLMIntentOutput(date_expression={"relative":"…SELECT 1 --"})` both VALIDATE → blocking
  finding 1.
- Cross-check: `bronze_ohlcv_day`/`gold_options_features`/`silver_ohlcv_day_adjusted`
  columns vs. `docs/DATA_SCHEMAS.md` and the corp-actions SQL → all match; zero
  `close AS adj_close` occurrences in the DDL.

## Gate

Not APPROVED. Round 4–5's substantive work is correct and verified, but the
round-1/check2 SQL-smuggling defect through `DateExpression.relative` is still open.
One focused fix (closed-set or hostile-content validation on `relative` + a red test)
is required before Codex final validation.
===VERDICT END===
