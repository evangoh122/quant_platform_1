# CHECK: corporate-actions round 9 (checker: DeepSeek)

Read-only. No network/secrets. Mutation proofs in /tmp copies (cp -r to /tmp/ca9-mut-*). Write .agents/deepseek/VERDICT-corporate-actions-round9.md
between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line, counts, mutation results.
Build request: .agents/requests/BUILD-corporate-actions-round9.md (from Codex .agents/codex/VERDICT-corporate-actions-review2.md). Commits: 7e39b74..HEAD.
1. jobs.yml + runbook: every corporate-actions source value is "massive"; the validation tests parse the real files. Mutation: put yfinance back in
   jobs.yml → FAILS. grep for remaining yfinance in corporate-actions wiring/docs.
2. Checkpoint ordering: MiMo says "3 structural tests" — the build asked for a FUNCTIONAL test: simulate a crash between fetch and append (writer
   raises) → resume with the same run_id must NOT skip the symbol and must write its rows. Is there such a test that actually runs the notebook's
   loop/function (not a source-text grep)? Mutation: move SUCCESS back before the append → a test FAILS. Also confirm the post-append key
   verification query really checks the batch's (symbol, ex_date, source) keys.
3. Rate limit inside the adapter before EVERY HTTP request (incl. pagination pages and retries); notebook loop sleep removed (no double sleep).
   Fake-clock test: N empty-result symbols → spacing ≥ delay. Mutation: remove the adapter sleep → FAILS. Retries: does the retry backoff stack
   with the delay sensibly?
No tests deleted/weakened (git diff 7e39b74..HEAD -- tests).
Run: python3 -m pytest -q tests/bronze tests/silver tests/test_security.py; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps same.
