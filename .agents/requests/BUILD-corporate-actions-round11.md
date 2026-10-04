# BUILD corporate-actions round 11 (builder: MiMo) — one resume edge case

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/corporate-actions. Descriptive commits. LF. NEVER delete or weaken tests.
Codex review: .agents/codex/VERDICT-corporate-actions-review3.md (1 blocking; everything else verified).

Resume after "append committed but SUCCESS not recorded": notebooks/refresh_bronze_corporate_actions.py ~368-375 removes existing bronze keys via the
anti-join and only verifies/checkpoints when new_rows is non-empty, so on resume a symbol whose rows already exist is refetched, classified as all
conflicts, and never verified or checkpointed — every resume repeats the fetch.
Fix (inside run_batch()): verify ALL fetched candidate keys for the symbol — new AND already-existing (conflict) keys — and record SUCCESS when every
key is present in bronze, even when new_rows is empty. Keep true conflicts (same key, different ratio) reported as conflicts (not silently SUCCESS):
state the rule you implement.
Regression test (functional, in-memory fakes): populated existing_keys_set with all of SYM's keys and no prior SUCCESS checkpoint → run_batch records
SUCCESS for SYM, writer not called, verifier called; a second resume skips SYM. Mutation (copy via `git archive HEAD | tar -x -C /tmp/<dir>`, paste
output): verify only new rows again → test FAILS.
Acceptance: python3 -m pytest -q tests/bronze tests/silver tests/test_security.py all pass; pyspark hidden
(PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps). .agents/mimo/VERDICT-corporate-actions-round11.md. Commit.
