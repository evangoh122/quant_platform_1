Checker: Claude Sonnet subagent (DeepSeek out of credit)

===VERDICT START===
# VERDICT: nl1-contracts (re-check, round 7)
**Status:** CHANGES_REQUESTED
**HEAD:** 462c03f (branch `slice/nl-contracts`)

Findings 1 and 2 from check4 are closed. Finding 3 (schema-walking audit) is not: the audit is blind to every nested model and only ever inspects one leaf.

## Blocking findings

1. **[tests/analytics_nl/test_contracts.py:733-753, `_get_string_leaves`, and :974-995] The schema-walking audit never resolves `$ref`, so it enumerates exactly one string leaf: `.semantic_model_version`.**
   - The `$ref` branch only follows a ref when `"$defs"` is in the same sub-schema. `$defs` exists only at the schema root, so refs inside properties, `items` and `anyOf` are never followed.
   - `LLMEntityMention.text`, `DateExpression.explicit_range` and the enum fields are never audited. I printed the leaves: only `.semantic_model_version` was returned.
   - `test_adding_new_free_string_field_fails` has the same blind spot. It does not mutate anything. It re-walks the live schema with a walker that has no `$ref` or `$defs` handling.
   - Mutations in a copy at `/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/chk-nl1r7/c`:
     - (A) Loosen `LLMEntityMention.text` to `str` and remove the validator: 11 failures. These come from the hostile-corpus and older behavioural tests, not the audit. OK.
     - (B) Remove only the `pattern` from the schema field, keeping the validator: the audit PASSES. Only `test_all_schemas_regenerate` fails.
     - (C) Add a free `note: str` to `LLMEntityMention`: the audit PASSES. Only the schema-sync test fails.
     - (D) Add a free `note: str` at the top level of `LLMIntentOutput`: the audit FAILS. This is the only case it catches.
   - Scenario: a developer adds a free string to a nested model and regenerates the schemas. Every test is then green, including the audit and the "mutation proof".
   - Requirement 3 was "enumerates every string leaf" and "add a new free str field → audit fails". Both are unmet for nested fields.
   - **Fix:**
     - Resolve `$ref` against the root `$defs` by passing the root schema or defs down through the recursion. Cover `properties`, `items`, `anyOf`, `allOf` and `prefixItems`.
     - Assert that the leaf set contains `LLMEntityMention.text` and the `explicit_range` start and end, so a walker that stops finding them fails loudly.
     - Accept an enum, `const`, a `format: date` leaf or a `pattern` leaf.
     - Make the mutation proofs real. Build a subclass or a dynamically created model with a free `str` field and assert the audit function raises. Likewise for a text field that has a pattern but is loosened.

2. **[tests/analytics_nl/test_contracts.py:783-935] The hostile corpus is applied only to `LLMEntityMention.text`, not to "every string leaf".**
   - Combined with finding 1, nothing exercises the other leaves with hostile input.
   - `DateExpression.relative`, `grouping` and `semantic_model_version` are the leaves that exist. These are enum or version-pattern leaves, and a hostile string there can only be rejected by that type.
   - **Fix:** drive the corpus from the leaves the fixed audit discovers, building a payload for each leaf path and asserting `ValidationError`.

## Non-blocking notes

- **Verified OK, item 1 (allowlist):**
  - `LLMEntityMention.text` is NFKC-normalised, matched against `^[A-Za-z0-9][A-Za-z0-9 .&'\-/_]{0,24}$`, and the same `pattern` is in `llm_intent_output.v1.json:76`.
  - I ran about 50 extra hostile strings. Rejected: fullwidth and Greek punctuation, fullwidth SQL keywords, zero-width, bidi, line-separator and tag characters, `<>$(){}` and quotes.
  - All 37 keys in `aliases_v1.yaml` are accepted.
  - The 90-plus corpus strings in the repo test are all rejected.
- **Residual: the allowlist is a character class, not a semantic filter.** These are accepted because they use only allowed characters: `disregard prior`, `ignore the above`, `act as admin`, `sudo rm`, `xp_cmdshell`, `pg_sleep 5`, `WAITFOR DELAY`, `COPY users`, `pragma x`, `AAPL/../x`, `1 OR 1`.
  - These are inert, because `text` is only an alias-lookup key. Consider tightening to drop `/` and `_` unless an alias needs them. Consider a spacing cap (for example at most 4 tokens).
  - Short reworded injections pass the allowlist. The previous round's "reworded injections must be rejected" criterion is met only for the listed phrases.
- The schema `pattern` permits `'`, but the validator rejects it through `_SQL_METACHAR_RE`. The advertised contract is therefore slightly looser than the enforced one. Remove `'` from the allowlist character class.
- `validate_text` still runs the old blacklist checks on top of the allowlist. Harmless, but the control-character and metachar checks are dead code.
- **Verified OK, item 2 (timezone):**
  - UTC 2026-03-09 02:00Z gives `ytd` end 2026-03-08.
  - UTC 2026-01-01 03:00Z gives `last_year` 2024-01-01 to 2024-12-31.
  - A naive clock raises `ValueError`.
- **Verified OK, item 4 (earlier guarantees):**
  - `export_schemas --check` prints "All schemas match."
  - The metric, put_call_ratio, Silver, no-SELECT-star, source-column, adj_close and split tests, 69 in all (selected with `-k`), all pass.

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/analytics_nl` → 268 passed.
- `python3 -m pytest -q -p no:cacheprovider tests --ignore=tests/lakebase` → 806 passed, 67 skipped.
- `python3 -m analytics_nl.export_schemas --check` → OK.
- Mutations A to D, run in a copy (results in finding 1).
- Ad-hoc hostile probe of about 50 strings plus all alias keys.
===VERDICT END===
