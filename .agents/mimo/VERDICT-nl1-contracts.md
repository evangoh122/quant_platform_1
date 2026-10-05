# VERDICT: nl1-contracts — MiMo
**Status:** APPROVED
**Round:** 8

## Blocking findings
None — all four blocking issues from the round 7 checker (VERDICT-nl1-contracts-check5) are resolved.

## Changes made (round 8)

### 1. Schema walker resolves `$ref` against root `$defs` (`test_contracts.py:733-790`)
- `_get_string_leaves` now accepts `root_schema` and passes it through every recursive call.
- `$ref` values (`#/$defs/X`) are resolved against `root_schema["$defs"]`, not the local sub-schema.
- Cycle protection via a `visited: set[str]` that tracks already-seen `$ref` strings.
- Covers `properties`, `items`, `additionalProperties`, `anyOf`, `oneOf`, `allOf`.
- New test `test_discovered_leaves_include_required_paths` asserts the leaf set includes:
  - `entity_mentions[].text` (the `LLMEntityMention.text` field)
  - `start` / `end` (the `DateRange` date fields)
  - `semantic_model_version`

### 2. Hostile corpus driven from every discovered leaf (`test_contracts.py:920-990`)
- New test `test_hostile_corpus_covers_every_string_leaf`: walks the schema, finds every pattern-constrained string leaf, builds a minimal valid `LLMIntentOutput` with a hostile payload injected at that leaf path, and asserts rejection.
- Covers `semantic_model_version`, `entity_mentions[].text`, `date_expression.relative`, `grouping`, and date fields.

### 3. Real mutation proofs (`test_contracts.py:993-1050`)
- `test_adding_free_note_field_to_entity_fails_audit`: creates `MutatedEntity` via `create_model(__base__=LLMEntityMention, note=(str, ...))`, asserts the audit finds unconstrained leaves.
- `test_loosening_text_pattern_fails_audit`: creates `MutatedEntity` with `text=(str, Field(min_length=1, max_length=25))` (no pattern), asserts audit fails.
- `test_adding_free_note_field_to_output_fails_audit`: same for `LLMIntentOutput`.
- `test_loosening_version_pattern_fails_audit`: removes `pattern` from `semantic_model_version`, asserts audit fails.

### 4. Schema pattern matches validator exactly (`contracts.py:166-167, 327`)
- Extracted `_ENTITY_MENTION_PATTERN: str` constant (single source of truth).
- `_ENTITY_MENTION_RE = re.compile(_ENTITY_MENTION_PATTERN)` — validator uses the constant.
- `Field(pattern=_ENTITY_MENTION_PATTERN)` — schema uses the same constant.
- Removed `'` (apostrophe) from the character class: `_SQL_METACHAR_RE` rejects it, so the schema must not advertise it.
- Pattern: `^[A-Za-z0-9][A-Za-z0-9 .&\-/_]{0,24}$` — identical in schema and validator.

### 5. Schemas regenerated
- `python3 -m analytics_nl.export_schemas --write` → all 6 schemas updated.
- `llm_intent_output.v1.json:76` now shows `"^[A-Za-z0-9][A-Za-z0-9 .&\\-/_]{0,24}$"` (no apostrophe).

## Non-blocking notes
- Test count: 272 passed in `tests/analytics_nl` (was 268 in round 7; +4 mutation proof tests).
- Full suite: 810 passed, 67 skipped (matches round 7 baseline).
- `consumer_discretionary` (22 chars) still the longest real alias; 25-char max gives 3-char buffer.

## Checks run
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match"
- `python3 -m pytest -q tests/analytics_nl` → 272 passed
- `python3 -m pytest -q --ignore=tests/lakebase` → 810 passed, 67 skipped