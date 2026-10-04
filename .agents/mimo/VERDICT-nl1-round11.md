# VERDICT: nl1-round11 — MiMo
**Status:** APPROVED
**Round:** 11

## Blocking findings
None.

## Fixes applied
1. `_SQL_METACHAR_RE` (contracts.py:161): changed from `r"[;]|--|/\*|\*/"` to `r"""["`\\;]|--|/\*|\*/"""`. Now rejects double-quote, backtick, backslash in addition to `;`, `--`, `/*`, `*/`. ASCII apostrophe NOT matched.
2. Added 15 new tests in test_aliases.py (`TestHostileInputRejection`): 7x `_reject_hostile` parametrized, 7x `resolve()` parametrized, 1x apostrophe acceptance. All `_reject_hostile` and `resolve()` now cover `a"b`, ``a`b``, `a\b`, `a;b`, `a--b`, `a/*b``, `a*/b`.
3. Duplicate `"metric"` key in `_make_valid_output`: AST analysis confirmed no duplicate exists in current code (only one `"metric": "price"` at line 1060). Checker finding from round 10 may have been resolved already or was a false positive.

## Non-blocking notes
- `_SQL_METACHAR_RE` is imported in aliases.py:25 from contracts — single source of truth maintained.
- Contract allowlist pattern (`_ENTITY_MENTION_PATTERN`) independently rejects these chars for LLM path; this fix restores defence-in-depth for the resolver path.

## Checks run
- `python3 -m pytest tests/analytics_nl -q` → 308 passed
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/analytics_nl -q` → 308 passed
- `python3 -m analytics_nl.export_schemas --check` → All schemas match
- Mutation proof: remove `"`/backtick/backslash from shared regex → 6 tests FAIL (a"b, a`b, a\b pass through unblocked)