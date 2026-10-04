# CHECK: corporate-actions round 10 (checker: DeepSeek)

Read-only. No network/secrets. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-corporate-actions-round10.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Your round-9 verdict: .agents/deepseek/VERDICT-corporate-actions-round9.md. Build request: .agents/requests/BUILD-corporate-actions-round10.md. Commit a39f599.
1. run_batch() is importable with injectable writer/checkpoint store; the notebook calls it. FUNCTIONAL crash test: writer raises after fetch → no
   SUCCESS; same run_id again → symbol NOT skipped, rows written; a truly succeeded symbol skipped. Mutation: SUCCESS before append → FAILS.
   Confirm no source-grep tests remain for this behaviour.
2. ALL-keys verification: 2 rows, 1 verified → not SUCCESS, re-fetched on resume. Mutation: ANY → FAILS.
3. Verification via DataFrame join (no SQL string splicing); a quote-bearing symbol handled.
4. ALSO check (found live by Claude): CLI mode reads the key with `WorkspaceClient().secrets.get_secret(...).value` — that value is BASE64-encoded,
   so every Massive request returned 401 in a live dry run. Is it decoded anywhere? (Notebook mode via dbutils returns plaintext.) Report as a finding.
No tests deleted/weakened except replaced source-grep tests (list them). Run: python3 -m pytest -q tests/bronze tests/silver tests/test_security.py;
pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps.
