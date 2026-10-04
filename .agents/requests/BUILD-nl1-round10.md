# BUILD nl1 round 10 (builder: MiMo; checker: Claude Sonnet subagent; reviewer: dataexpert Claude)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/nl-contracts. Commit after each item with a
descriptive message. NEVER delete or weaken existing tests.
Checker verdict: .agents/deepseek/VERDICT-nl1-round9.md (CHANGES_REQUESTED). Items 2–5 of round 9 verified.

## 1 (blocking). Hostile-corpus test is vacuous
`_make_valid_output` (tests/analytics_nl/test_contracts.py ~1084) passes enum values as strings to a strict model, so
the baseline itself fails with 4 ValidationErrors and every (leaf, payload) "rejects".
- Build the baseline with `model_validate_json(json.dumps(base))` (JSON mode accepts enum strings) or with enum instances.
- Add an explicit assertion that the unmodified baseline VALIDATES (a separate test, and also asserted at the top of the corpus test).
- Narrow `except (ValidationError, Exception)` (~1157) to `except ValidationError`; any other exception must fail the test.
- Mutation proof (in /tmp copy, report output): `_ENTITY_MENTION_PATTERN = r"^.{1,25}$"` → `test_hostile_corpus_covers_every_string_leaf` FAILS.

## 2. End-to-end apostrophe consistency
`analytics_nl/aliases.py:28` has its own `_SQL_METACHAR_RE` including `'`, so `_reject_hostile("McDonald's")` returns
"sql_metacharacters": the contract accepts and the resolver rejects. Make aliases.py reuse the single source of truth
from contracts.py (import the constant/regex; no second copy). Test: the five names (McDonald's, Lowe's, Macy's,
Kohl's, Dick's, both ' and ’ forms) pass the contract AND the resolver's hostile check; `x'; DROP TABLE t; --` fails both.

## 3. Minor
- The before-validator must not mutate the caller's dict in place (copy first). Test: input dict unchanged after validate.
- Fullwidth apostrophe U+FF07 is accepted after NFKC → that's fine; add a test documenting it.

## Acceptance
- python -m pytest tests/analytics_nl -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) all pass.
- `python -m analytics_nl.export_schemas --check` → all match.
- .agents/mimo/VERDICT-nl1-round10.md with counts + mutation output. Commit everything.
