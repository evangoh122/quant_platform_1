# BUILD: NL1 round 6 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests.

DeepSeek check3 (`.agents/deepseek/VERDICT-nl1-contracts-check3.md`): `DateExpression.relative`
(`analytics_nl/contracts.py:~318`) is a free-form `str` (1–50 chars) with no validation, so
`"last month'; DROP TABLE gold_options_features; --"` validates. The LLM output contract must be
fail-closed on its own.

Fix:
- Make `relative` a closed `Enum` (`RelativeDate`) with exactly the phrases `resolve_relative_date`
  supports, plus any obvious ones you add with resolver support and tests: e.g. last_week,
  last_month, last_quarter, last_year, ytd, mtd, qtd, last_5_days, last_30_days, last_90_days,
  last_252_days. Each value needs: its canonical wire value, aliases handled in the deterministic
  alias layer (NOT in the LLM schema), and a resolver implementation in America/New_York with an
  injected clock.
- Audit EVERY remaining free-form `str` field in `LLMIntentOutput` and its nested models. Each must
  be an enum, an ISO date with a validator, or a validated `LLMEntityMention.text`-style field.
  List them in the verdict.
- Tests:
  - SQL / injection strings in `relative` are rejected;
  - every enum value resolves correctly, including DST edges;
  - a property test fuzzes random strings into every string field of `LLMIntentOutput` and asserts
    that only allow-listed patterns validate.
- Regenerate the JSON schemas, and keep the sync test green.

Run `python3 -m pytest -q tests/analytics_nl` and the full suite with `--ignore=tests/lakebase`.
LF line endings only. Don't touch `.agents/dispatch.sh`. Update `.agents/mimo/VERDICT-nl1-contracts.md`
(round 6).
