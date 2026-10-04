# BUILD nl1 round 11 (builder: MiMo) — small fix

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/nl-contracts. Descriptive commit messages.
NEVER delete or weaken existing tests. Checker verdict: .agents/deepseek/VERDICT-nl1-round10.md.

1 (blocking). The resolver lost double-quote / backtick / backslash rejection: `_reject_hostile` (aliases.py:61-68) now uses
   contracts.`_SQL_METACHAR_RE` = `[;]|--|/\*|\*/`, so `a"b`, ``a`b``, `a\b` return None.
   Fix: the single shared regex in contracts.py must reject `"`, backtick, `\`, `;`, `--`, `/*`, `*/` (everything the
   pre-round-9 resolver rejected EXCEPT the ASCII apostrophe). Both contract and resolver use it.
   Tests in tests/analytics_nl/test_aliases.py: `_reject_hostile` and `resolve()` reject each of `a"b`, ``a`b``, `a\b`,
   `a;b`, `a--b`, `a/*b`, `a*/b`; accept McDonald's / Lowe's (both apostrophe forms).
   Mutation proof (in /tmp copy, paste output): remove `"` from the shared regex → a resolver test FAILS.
2. Minor: remove the duplicate "metric" key in `_make_valid_output` (tests/analytics_nl/test_contracts.py ~1060).

Acceptance: python -m pytest tests/analytics_nl -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) all pass;
python -m analytics_nl.export_schemas --check passes. .agents/mimo/VERDICT-nl1-round11.md. Commit everything.
