# BUILD nl1 round 9 (builder: MiMo; checker: Claude Sonnet subagent standing in for DeepSeek)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/nl-contracts. Commit after each item.
NEVER delete or weaken existing tests.
Checker verdict: .agents/deepseek/VERDICT-nl1-round8.md (CHANGES_REQUESTED). The $ref audit fix is verified.

## 1 (blocking). Hostile corpus over EVERY string leaf, EVERY payload
`test_hostile_corpus_covers_every_string_leaf` (tests/analytics_nl/test_contracts.py ~1085-1118) skips enum/date leaves,
samples `[:20]`, `break`s on first rejection, and only asserts `tested_leaves > 0`.
Rewrite: for each string leaf discovered by THE audit walker (the same function the audit test uses), for EVERY payload in the
corpus, build an otherwise-valid intent with that payload at that leaf and assert the model rejects it (enum/date/pattern
leaves included — an enum leaf rejects by membership, a date leaf by format; a leaf that accepts a hostile payload is a failure).
Assert the set of leaves exercised == the full discovered leaf set (exact equality). Use pytest parametrization or collected
failures so one run reports all accepting (leaf, payload) pairs.
Mutation proof (in /tmp copy, report output): a free `note: str` nested behind a $ref → this test FAILS (not only the audit test).

## 2. Exact leaf paths
`test_discovered_leaves_include_required_paths`: assert the discovered set EQUALS an explicit expected set of all 8 paths
(the checker independently found 8 string leaves in llm_intent_output.v1.json).

## 3. Walker correctness
Handle `prefixItems`; track `visited` refs per path (copy on descent) so sibling branches that reuse a $ref are both walked,
while true cycles still terminate. Test: a schema where two sibling properties $ref the same def → both leaf paths found;
a self-referential def → terminates.

## 4. One walker
`TestMutationProofs` has its own third copy of the walker. Delete the copies; all tests import the single walker.

## 5. Apostrophes in company names (owner-facing decision by Claude)
Users will type "McDonald's", "Lowe's", "Macy's", "Kohl's", "Dick's". Entity text is only matched against the allowlist and is
never interpolated into SQL, so ALLOW the ASCII apostrophe (U+0027) and normalize U+2019 (’) to U+0027 before validation.
Keep every other SQL metacharacter (; -- /* */ " ` \ etc.) rejected. Update `_ENTITY_MENTION_PATTERN` (single constant),
regenerate the JSON schema via the repo exporter, and fix the error message at contracts.py ~337.
Tests: those five names accepted (both apostrophe forms); `x'; DROP TABLE t; --` still rejected (by the other metachars).
Add a dedicated test asserting the JSON schema pattern == `_ENTITY_MENTION_PATTERN`.

## Acceptance
- python -m pytest tests/analytics_nl -q; full suite `python -m pytest -q --ignore=tests/lakebase`; pyspark hidden
  (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) analytics_nl — all pass.
- `python -m analytics_nl.export_schemas --check` → all match.
- .agents/mimo/VERDICT-nl1-round9.md with counts + mutation output. Commit everything.
