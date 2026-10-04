# NL1 round 11 verdict
Checker: Claude Sonnet subagent (DeepSeek out of credit)
Range: 3d62307..7216e2e. Verdict: **APPROVED**

1. Shared regex: contracts.py:161 `_SQL_METACHAR_RE = ["`\;]|--|/\*|\*/` (no apostrophe). aliases.py:25 imports it, used at aliases.py:64; grep shows no second copy in analytics_nl/. Run by me: `_reject_hostile` rejects a"b, a`b, a\b, a;b, a--b, a/*b, a*/b; accepts McDonald's, Lowe's, and U+2019 forms. Contract accepts McDonald's / Lowe's (U+2019 normalized to '), rejects `x'; DROP TABLE t; --` and a"b.
2. Tests: tests/analytics_nl/test_aliases.py:168-201 parametrize all 7 strings through `_reject_hostile` and `resolve()`; plus apostrophe accept test. Mutation in /tmp/nl1r11-mut (remove `"` from regex): 2 FAILED (reject_hostile[a"b], resolve[a"b]), 306 passed.
3. AST check over tests/analytics_nl/test_contracts.py: no dict literal with duplicate constant keys (none at HEAD; the round-11 diff does not touch test_contracts.py, so nothing to remove).
4. Mutation `_ENTITY_MENTION_PATTERN = ^.{1,25}$`: 4 FAILED (TestHostileCorpus x3 incl. covers_every_string_leaf, test_all_schemas_regenerate).
5. `git diff 3d62307..HEAD -- tests`: additions only (35 lines), zero deletions.

Runs: pytest tests/analytics_nl: 308 passed (with and without pyspark-hidden PYTHONPATH); export_schemas --check: "All schemas match."
Findings: none blocking. Note: MiMo's claim about removing a duplicate "metric" key was a no-op (none existed), harmless.
