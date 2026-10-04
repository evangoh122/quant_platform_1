# VERDICT nl1 round 10 (f00cd8a..HEAD)
Checker: Claude Sonnet subagent (DeepSeek out of credit)
**CHANGES_REQUESTED** (one regression, items 1/3/4 verified OK)

Tests: `pytest tests/analytics_nl` 293 passed; with pyspark hidden 293 passed; `export_schemas --check` "All schemas match."

## Verified OK
1. Hostile corpus (tests/analytics_nl/test_contracts.py): baseline built via model_validate_json(json.dumps(...)) (:1127, :1141, :1153); separate test `test_hostile_corpus_baseline_validates` (:1123) plus assertion at top of corpus test; `except ValidationError` only (:1155); exercised-set == discovered-set assertion (:1160-1164) retained.
   - Mutation A (/tmp/nl1r10-mut-a) `_ENTITY_MENTION_PATTERN = r"^.{1,25}$"`: `test_hostile_corpus_covers_every_string_leaf` FAILS (also the 2 other hostile tests fail).
   - Mutation B (/tmp/nl1r10-mut-b) baseline operation "trend"->"BOGUS": `test_hostile_corpus_baseline_validates` FAILS and the corpus test FAILS (vacuity guard works).
3. Validator copies dict: contracts.py:335 `data = dict(data)`; test_validator_does_not_mutate_input_dict (test_contracts.py ~1219); U+FF07 test exists (~1228).
4. Tests diff f00cd8a..HEAD: only 3 removed lines (docstring, `LLMIntentOutput(**output_data)` -> JSON form, `except (ValidationError, Exception)` narrowed). No tests deleted or weakened.
2a. Single regex: aliases.py:25 imports `_SQL_METACHAR_RE` from contracts; no second copy in analytics_nl/ (grep). Five apostrophe names (' and U+2019) pass contract and `_reject_hostile`; `x'; DROP TABLE t; --` rejected by both.

## Finding 1 (CHANGES_REQUESTED): resolver lost quote rejection
Old aliases.py:28 (f00cd8a) `[;'\"]|--|/\*|\*/`; contracts.py:161 `[;]|--|/\*|\*/` (no quote chars). After import, `_reject_hostile` (aliases.py:61-68) now returns None for `a"b`, ``a`b``, `a\b` (verified by running it). `;`, `--`, `/*`, `*/` still rejected. The contract still rejects `"`, backtick, `\` (via allowlist pattern, contracts.py:166), so LLM path is safe, but the resolver (public `resolve()` on arbitrary text) lost defence-in-depth for double quote, and no test covers it (test_aliases.py:143-166 only tests `'`, `;`, `--`). Fix: keep single source but add a shared regex/helper in contracts.py (e.g. `_SQL_METACHAR_RE` plus `"` and backtick/backslash, with `'` handled separately), or a resolver check using the contract's allowlist; add resolver tests for `"`, backtick, `\`, `/*`, `*/`.

## Minor
- Duplicate key `"metric": "price"` in `_make_valid_output` (test_contracts.py ~1060); harmless, clean up.
