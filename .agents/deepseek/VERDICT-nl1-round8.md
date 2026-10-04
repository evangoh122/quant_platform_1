# Verdict: NL1 round 8 (commit a2609f6, diff 6bf7f78..a2609f6)

Checker: Claude Sonnet subagent (DeepSeek out of credit)

**Verdict: CHANGES_REQUESTED** (the blocking check5 defect is fixed; the remaining gaps are test-strength items against the round-8 spec)

## Test counts
- `pytest tests/analytics_nl -q`: 272 passed.
- Full `pytest -q --ignore=tests/lakebase`: 810 passed, 67 skipped.
- pyspark hidden (PYTHONPATH=.../scratchpad/nps), analytics_nl: 272 passed.
- `python -m analytics_nl.export_schemas --check`: "All schemas match." Independent regeneration equals the committed files (all 6).

## Verified
1. Audit resolves `$ref`: `tests/analytics_nl/test_contracts.py:730-790` (`_resolve_ref`, `_get_string_leaves`). It handles properties, items, additionalProperties (dict), anyOf, oneOf, allOf, and has cycle protection. My own walker in /tmp/nl1chk/walk.py (also covering prefixItems etc.) finds 8 string leaves in the real `llm_intent_output.v1.json`: semantic_model_version, operation, metric, entity_mentions[].text, grouping, date_expression.relative, explicit_range.start, explicit_range.end. MiMo's walker returns the identical 8. Match.
2. Single source of truth: `contracts.py:166-167` defines `_ENTITY_MENTION_PATTERN`/`_RE`; the field at `contracts.py:328` uses the constant; the validator at `:334` uses `_RE`. Schema JSON line 76 matches. No documented example or test uses an apostrophe (grep of aliases_v1.yaml, plan, tests: none). `McDonald's` and `Macy's` are now REJECTED. This is acceptable (the alias data has no apostrophe names), but it is a deliberate behaviour change. `AT&T`, `S&P 500` pass.
3. Mutation proofs, run in /tmp/nl1-mut-{a,b,c,d} copies:
   - (a) a free `note: str` nested behind a `$ref` on LLMIntentOutput: `test_all_string_leaves_are_constrained` FAILS ("Unconstrained string leaf at .extra|0.note"). The hostile tests still pass.
   - (b) pattern dropped from `LLMEntityMention.text`: the audit test FAILS, and so does the schema-sync test.
   - (c) the JSON schema pattern edited to differ from the constant: `test_all_schemas_regenerate` FAILS. There is no dedicated constant-vs-schema test; sync is the only guard.
   - (d) the constant changed and the schemas regenerated: 272 pass, as expected for a single source.
4. Test removals: only 2 test functions removed, and both were replaced by stricter ones. `test_loosening_text_to_free_string_fails` (21-payload check) is covered by `test_hostile_payloads_rejected_by_entity_mention` (the full corpus). `test_adding_new_free_string_field_fails` (a non-mutating tautology) is replaced by real create_model mutation tests. The 116 deletions are the old walker, the old mutation tests and the corpus re-encoded from literal invisible characters to `\uXXXX` escapes; the corpus payload count is preserved. No assertion was weakened.

## Findings (changes requested)
1. `test_contracts.py:1085-1118` (`test_hostile_corpus_covers_every_string_leaf`) does not meet round-8 item 2. It SKIPS every enum/const leaf and every date-format leaf (`:1093-1097`), so in practice only entity text and semantic_model_version are exercised. Of the 8 discovered leaves, `_build_payload_for_leaf` (`:1038`) returns None for operation, metric and grouping. It uses only `HOSTILE_PAYLOADS[:20]`, `break`s on the first rejection, swallows `except (ValidationError, Exception)`, and its only assertion is `tested_leaves > 0`. It would pass with a single guarded leaf. It also did not fail under mutation (a). Fix: assert per leaf that EVERY payload is rejected, including enum and date leaves, and fail if `_build_payload_for_leaf` returns None for a discovered leaf.
2. `test_contracts.py:~1060-1080` (`test_discovered_leaves_include_required_paths`) uses loose substring checks (`"start" in p or "end" in p`). It does not assert the explicit paths, such as `.date_expression.explicit_range|0.start` and `.end`, nor each enum field (operation, metric, grouping, relative). Assert the exact expected set.
3. The walker has no `prefixItems` handling (the lead asked for it; `:772-800`). `visited` is shared across siblings, so a `$ref` used a second time is skipped, which is benign for the constraint audit but hides the second path from the hostile test. Use a per-path stack.
4. `TestMutationProofs` (`:1144-1190`) carries a THIRD copy of the walker (no additionalProperties) instead of calling the audited one. The audit and the mutation proof can drift. Share one module-level walker and a shared `assert_all_leaves_constrained(schema)`, so the mutation tests exercise the production audit and not a copy.
5. Minor: the error message at `contracts.py:337` still says "apostrophe". Update it.
