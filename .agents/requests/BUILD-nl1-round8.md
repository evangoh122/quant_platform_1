# BUILD: NL1 round 8 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests.

Checker (`.agents/deepseek/VERDICT-nl1-contracts-check5.md`): the allowlist, timezone fix and earlier
guarantees are VERIFIED. One blocking issue: **the schema-walking audit is blind.**

- `_get_string_leaves` doesn't resolve `$ref` against the ROOT `$defs`, so it finds only
  `semantic_model_version`, and never `LLMEntityMention.text` or the date fields.
- The "mutation proofs" don't mutate anything.
- The hostile corpus only targets one field.

Fix:
1. **Resolve every `$ref`** (`#/$defs/X`) against the root schema, recursively, through `anyOf`,
   `oneOf`, `allOf`, `items`, `properties` and `additionalProperties`, with cycle protection.
   Assert that the discovered leaf set INCLUDES at least `entity_mentions[].text`, every date field,
   and every enum-typed field, by explicit path.
2. **Drive the hostile corpus from the discovered leaves.** For EVERY string leaf, build a minimal
   valid `LLMIntentOutput` and put each hostile payload into that leaf. All must be rejected (enum,
   date or pattern).
3. **Real mutation proofs** (tests that build a mutated MODEL in-process): create a subclass or
   dynamic pydantic model that adds a free `note: str` to the entity model, or removes the `pattern`
   from `text`, run the audit function against its schema, and assert the audit FAILS. Do this for
   both mutations.
4. **Make the schema `pattern` match the validator exactly.** The pattern currently allows `'` but
   the validator rejects it. One source of truth: generate the pattern from the same constant the
   validator uses.

Regenerate the schemas. Run `python3 -m pytest -q tests/analytics_nl` and the full suite with
`--ignore=tests/lakebase`. LF line endings only. Don't touch `.agents/dispatch.sh`. Update
`.agents/mimo/VERDICT-nl1-contracts.md` (round 8).
