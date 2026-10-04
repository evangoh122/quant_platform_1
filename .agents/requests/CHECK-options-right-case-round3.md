# CHECK: options-right-case round 3 (checker: DeepSeek)

Read-only for source. Mutation proofs in /tmp copies (cp -r to /tmp/optcase3-mut-*). Write .agents/deepseek/VERDICT-options-right-case-round3.md
between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line, counts, mutation results.
Build request: .agents/requests/BUILD-options-right-case-round3.md (from Codex review .agents/codex/VERDICT-options-right-case-review.md).
Commits: 8af3d7f..HEAD.
Verify:
1. `_shape_day()` uses ONE directly tested canonicalisation function, and a test runs `_shape_day()` itself. Codex's exact mutation: change
   `_shape_day()` to emit lowercase 'put'/'call' → a test FAILS (MiMo reported a different mutation — run Codex's).
2. gold/02: day CTE and p25/c25 quote CTEs map PUT/put/P → PUT and CALL/call/C → CALL before comparing; DuckDB semantic fixtures include P/C
   rows and the extracted real SQL counts them. Mutation: drop 'P' from the alias list → FAILS.
3. docs/DATA_SCHEMAS.md lists per-writer encodings (refresh day 'PUT'/'CALL', refresh quotes 'put'/'call', Quick Start 'P'/'C') and the
   consumer normalisation rule.
4. Maintenance SQL is LF; the CRLF test fails if a CRLF line is reintroduced (mutation).
5. No tests deleted/weakened: git diff 8af3d7f..HEAD -- tests.
Run: python3 -m pytest -q tests/gold tests/bronze tests/silver (pre-existing pytz failures known); pyspark hidden
PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps same.
