# VERDICT: nl1-round10 — MiMo
**Status:** APPROVED
**Round:** 10

## Blocking findings
- (none)

## Non-blocking notes
- Item 1: Hostile-corpus test fixed with `model_validate_json(json.dumps(...))`. Baseline validation assertion added. Exception handler narrowed to `except ValidationError`. Mutation proof: weakening `_ENTITY_MENTION_PATTERN` to `r"^.{1,25}$"` causes 58 hostile payloads to slip through → test FAILS. Confirmed via file-swap in /tmp.
- Item 2: `aliases.py` now imports `_SQL_METACHAR_RE` from `contracts.py` — single source of truth. Duplicate regex removed. Apostrophe names (McDonald's, Lowe's, etc.) pass both contract and resolver. SQL injection with apostrophe rejected by both.
- Item 3a: `LLMEntityMention._normalize_text` copies input dict before mutation. Test confirms caller's dict unchanged after validate.
- Item 3b: Fullwidth apostrophe U+FF07 normalizes to U+0027 via NFKC, accepted by contract. Test added.

## Checks run
- `python -m pytest tests/analytics_nl -q` → 293 passed (PYTHONPATH with pyspark hidden)
- `python -m analytics_nl.export_schemas --check` → All schemas match
- Mutation proof (file-swap in /tmp) → test_hostile_corpus_covers_every_string_leaf FAILS with weakened pattern (58 payloads accepted)

## Files modified
- `analytics_nl/contracts.py:335` — copy dict before mutation in `_normalize_text`
- `analytics_nl/aliases.py:25` — import `_SQL_METACHAR_RE` from contracts; remove duplicate
- `tests/analytics_nl/test_contracts.py:1120-1155` — baseline validation, `model_validate_json`, narrowed exception
- `tests/analytics_nl/test_contracts.py:1216-1231` — dict mutation test, fullwidth apostrophe test
- `tests/analytics_nl/test_aliases.py:169-193` — `TestApostropheConsistency` class

## Commit
`722295f` on `slice/nl-contracts`