# VERDICT: nl1-round9 — MiMo
**Status:** APPROVED
**Round:** 9

## Blocking findings
(none)

## Non-blocking notes
- Walker produces `|0` suffix for nullable anyOf variants (e.g. `.grouping|0` instead of `.grouping`). This is correct behavior — the anyOf has two branches (enum|null), and the enum is branch 0. The expected leaf set was updated to match.
- `_SQL_METACHAR_RE` no longer rejects standalone apostrophes; the allowlist pattern + `_SQL_KEYWORD_RE` + `_PROMPT_INJECTION_RE` provide layered defense. SQL injection payloads like `"x'; DROP TABLE t; --"` are still rejected (by keyword check).
- Pydantic v2 Field `pattern` is checked before `field_validator`, so smart apostrophe normalization uses `model_validator(mode="before")` instead.

## Checks run
- `python -m pytest tests/analytics_nl/test_contracts.py -q` → 91 passed
- `python -m pytest tests/analytics_nl -q` → 279 passed
- `python -m analytics_nl.export_schemas --check` → "All schemas match."
- `python -m pytest -q --ignore=tests/lakebase --ignore=tests/rag` → 535 passed, 58 skipped, 8 errors (all pre-existing `psycopg` import errors in tests/api/)
- `python -m pytest tests/analytics_nl/test_contracts.py::TestMutationProofs -v` → 4 passed
- `python -m pytest tests/analytics_nl/test_contracts.py::TestWalkerCorrectness -v` → 3 passed

## Implementation summary

### Item 1: Hostile corpus covers every string leaf
Rewrote `test_hostile_corpus_covers_every_string_leaf`: for each of the 8 discovered string leaves AND every payload in the corpus, builds a valid intent with that payload at that leaf and asserts rejection. Enum leaves reject by membership, date leaves by format, pattern leaves by content. Asserts exact leaf set equality and no (leaf, payload) pair accepted.

### Item 2: Exact leaf paths
`test_discovered_leaves_include_required_paths` now asserts the discovered set EQUALS the explicit expected set of 8 paths (including `|0` anyOf suffixes).

### Item 3: Walker correctness
- `prefixItems` support added to walker
- `visited` set is copied on descent (not mutated) so sibling branches that reuse a `$ref` are both walked
- Three new tests: `test_sibling_ref_reuse_both_walked`, `test_self_referential_def_terminates`, `test_prefix_items_walked`

### Item 4: One walker
Deleted 3 copies of the walker (TestSchemaWalkingAudit, TestHostileCorpus, TestMutationProofs). All tests now import the single module-level `get_string_leaves` and `assert_all_leaves_constrained`.

### Item 5: Apostrophes in company names
- `_ENTITY_MENTION_PATTERN` updated: `^[A-Za-z0-9][A-Za-z0-9 .&\-/'_]{0,24}$`
- `_SQL_METACHAR_RE` updated: `[;]|--|/\*|\*/` (no standalone apostrophe rejection)
- `model_validator(mode="before")` normalizes U+2019 → U+0027 before Field pattern check
- JSON schema regenerated and verified
- Tests: 5 apostrophe names accepted (both forms), smart apostrophe normalized, SQL injection with apostrophe still rejected, schema pattern == constant