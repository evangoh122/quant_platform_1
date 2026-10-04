# CHECK: corporate-actions round 11 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-corporate-actions-round11.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Build request: .agents/requests/BUILD-corporate-actions-round11.md (from Codex .agents/codex/VERDICT-corporate-actions-review3.md). Commit 4ef30e2.
Rerun Codex's probe: populated existing_keys_set with all of SYM's keys and no prior SUCCESS → run_batch records SUCCESS, writer not called, verifier
called; a second resume skips SYM. Mutation: verify only new rows → the test FAILS. Check the stated rule for TRUE conflicts (same key, different
ratio) — they must not be silently marked SUCCESS. Confirm earlier fixes still hold (ALL-keys, SUCCESS after append, adapter delay, key decode).
No tests deleted/weakened. Run python3 -m pytest -q tests/bronze tests/silver tests/test_security.py; pyspark hidden
PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps.
