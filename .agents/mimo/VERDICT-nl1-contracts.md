# VERDICT: nl1-contracts — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
(none)

## Non-blocking notes
- `DateExpression.relative` is now a closed `RelativeDate` enum with 11 values. SQL/injection strings are rejected at the schema level.
- All remaining free-form `str` fields in `LLMIntentOutput` and nested models are fail-closed:
  - `LLMIntentOutput.semantic_model_version` — validated against exact `SEMANTIC_MODEL_VERSION`
  - `LLMEntityMention.text` — validated with control char, SQL metachar, and prompt injection checks
  - `DateExpression.relative` — now enum (was free-form `str`)
- `resolve_relative_date` now supports all 11 `RelativeDate` values with aliases handled in the deterministic alias layer (not in LLM schema).

## Checks run
- `python3 -m pytest -q tests/analytics_nl` → 258 passed
- `python3 -m pytest -q --ignore=tests/lakebase` → 796 passed, 67 skipped
- `wsl file ...` on all changed files → LF only
- `wsl git diff --name-only` → 5 expected files changed, no secrets, no `.agents/dispatch.sh`
- `python3 -m analytics_nl.export_schemas --write` → schemas regenerated

## Summary of changes

### analytics_nl/contracts.py
- Added `RelativeDate` enum with 11 values: last_week, last_month, last_quarter, last_year, ytd, mtd, qtd, last_5_days, last_30_days, last_90_days, last_252_days
- Changed `DateExpression.relative` from `Annotated[str, Field(min_length=1, max_length=50)]` to `RelativeDate | None`

### analytics_nl/aliases.py
- Added `timedelta` import
- Extended `resolve_relative_date` to support all 11 `RelativeDate` values
- Added alias map for natural-language forms (e.g. "last month" → `last_month`)
- All date math uses `America/New_York` timezone with injected clock

### analytics_nl/schemas/llm_intent_output.v1.json
- Regenerated: `relative` field now references `RelativeDate` enum instead of free-form string

### tests/analytics_nl/test_contracts.py
- Added `TestRelativeDateEnum` class (10 tests): SQL injection, enum validation, count check
- Added `TestLLMStringFieldProperty` class (3 tests): adversarial string rejection property test
- Updated `TestLLMIntentOutput.test_valid_llm_output` to use `RelativeDate.last_month`

### tests/analytics_nl/test_aliases.py
- Added `TestAllRelativeDateValues` class (20 tests): all enum values resolve correctly, DST edges, leap year, year boundary