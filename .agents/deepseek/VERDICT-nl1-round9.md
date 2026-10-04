# VERDICT NL1 round 9
Checker: Claude Sonnet subagent (DeepSeek out of credit)
Verdict: CHANGES_REQUESTED

Round 9 = c930be0..HEAD (2e49c2f, 3655467). MiMo's self-verdict not used as evidence.

## Blocking findings

1. (BLOCKING) The hostile-corpus leaf test is VACUOUS. tests/analytics_nl/test_contracts.py:1084 `_make_valid_output` builds a dict with
   string enum values ("trend", "price", "last_month", "day"), and :1155 calls `LLMIntentOutput(**output_data)`. The model is
   strict (FrozenStrictModel): python-mode input needs enum INSTANCES. The baseline "valid" payload itself is rejected with 4
   ValidationErrors (operation, metric, date_expression.relative, grouping: "Input should be an instance of ..."; reproduced
   with `LLMIntentOutput(**_make_valid_output())`). So every (leaf, payload) pair "rejects" regardless of the payload, and
   `accepting` is always empty. Mutation proof: in /tmp copy, set `_ENTITY_MENTION_PATTERN = r"^.{1,25}$"`:
   test_hostile_corpus_covers_every_string_leaf STILL PASSES (only the two older entity-mention tests fail). The test cannot detect
   an accepting leaf. Additionally :1157 `except (ValidationError, Exception)` swallows any error (TypeError etc.) as "rejected".
   Fix: build the valid base from enum instances (or use model_validate_json / json.dumps, which works), assert the baseline
   (payload = a known-good value per leaf) is ACCEPTED first, narrow the except to ValidationError, and keep the mutation proof above as a test/CI check.
2. (Non-blocking, functional gap) analytics_nl/aliases.py:28 still has `_SQL_METACHAR_RE = r"[;'\"]|--|/\*|\*/"` and aliases.py:60-64/110
   `_reject_hostile` rejects any apostrophe: `_reject_hostile("McDonald's")` returns "sql_metacharacters". The contract now accepts
   McDonald's but the resolver rejects it as hostile, so the owner's intent (users can type these names) is not met end to end.
   Needs the same decision applied in aliases.py (allow ' and normalize U+2019 in _normalize/_reject_hostile) plus a resolver test.
   Only users of the contracts.py regex: contracts.py:348 (LLMEntityMention only); aliases.py has its own separate copy, so the
   contracts.py change did not open apostrophes anywhere else.

## Item-by-item
1. Coverage structure OK but not effective: loops all leaves x all payloads, no sampling/break (:1141-1159); enum/date leaves mapped in
   `_build_payload_for_leaf` (:1086-1122); untested-leaf check (:1162). Mutation (note: str = "x" on LLMEntityMention, nested behind $ref):
   test_hostile_corpus_covers_every_string_leaf FAILS (via "never tested", build returns None), as do test_all_string_leaves_are_constrained
   and test_discovered_leaves_include_required_paths. The mutation requirement is met, but see finding 1 for the real-rejection flaw.
   Minor: "exercised == discovered" is asserted as `discovered - tested` empty (equivalent since tested is a subset).
2. PASS. EXPECTED_LEAF_PATHS explicit 8 paths (~:826-835), exact set equality assert at test_discovered_leaves_include_required_paths.
3. PASS. get_string_leaves (:21-77): prefixItems handled, `visited = visited | {ref}` per-path copy. Tests test_sibling_ref_reuse_both_walked,
   test_self_referential_def_terminates, test_prefix_items_walked pass. (Self-ref test only asserts .root.label present; adequate.)
4. PASS. Single walker `get_string_leaves` at :21; grep finds no other walker/_resolve_ref copies in tests (TestMutationProofs uses assert_all_leaves_constrained).
5. Apostrophe, own python checks: McDonald's/Lowe's/Macy's/Kohl's/Dick's accepted in ASCII and U+2019 forms (normalized to '), also via
   LLMIntentOutput.model_validate_json nested in entity_mentions. Rejected: `x'; DROP TABLE t; --`, `;`, `--`, `/*`, `*/`, `"`, backtick, backslash, leading `'`,
   `drop's` (SQL keyword), U+02BC. Note: `x' OR 1` and fullwidth U+FF07 (NFKC -> ') are accepted; consistent with the owner decision.
   Normalization is a mode="before" model_validator on LLMEntityMention (contracts.py:330-336), so it covers every nested use of the model; it mutates the
   caller's input dict in place (minor, suggest copying). Dedicated pattern test present (test_entity_mention_pattern_matches_json_schema); the JSON schema
   regenerated (`export_schemas --check`: All schemas match). Mutations: remove U+2019 replace -> 2 tests fail; drop ' from pattern -> 3 tests fail.
   Error message at contracts.py:343 updated.
6. PASS. No test function names removed (comm of old/new `def test_` names empty; 84 -> 91 tests). Diff is +241/-243 in test_contracts.py only; deletions are the walker copies/weak assertions.
7. Counts. tests/analytics_nl: 279 passed (default) and 279 passed (pyspark-hidden PYTHONPATH). export_schemas --check: All schemas match.
   Full suite: the worktree .venv lacks deps (numpy, pandas, duckdb, polars, loguru, requests, psycopg, ibapi unsatisfiable), so I built a /tmp venv
   (requirements minus ibapi): HEAD = 39 failed, 669 passed, 41 skipped, 23 errors; baseline c930be0 in the same env = 39 failed, 662 passed, 41 skipped, 23 errors.
   Delta = +7 passed (the 7 new tests), identical failures/errors, so nothing was removed. MiMo's "535 pass" vs round 8's 810 is an environment difference
   (different venv/missing deps), not deleted tests; the exact 810 figure could not be reproduced here (missing deps), only the delta vs baseline.

## Required for next round
- Fix finding 1 (blocking) with a baseline-accepted check, ValidationError-only except, and the loosened-pattern mutation proof.
- Resolve finding 2 in aliases.py (or get owner sign-off that resolver keeps rejecting apostrophes).
