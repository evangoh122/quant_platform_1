# CHECK: rag-eval-harness round 10b (checker: DeepSeek) — re-check of one fix

Read-only for source. Your round-10 verdict (.agents/deepseek/VERDICT-rag-eval-harness-round10.md) had one blocker: no regression test
that the guard's socket default timeout is restored. Claude added it in the latest commit ("test(rag): regression test that the network
guard's socket default timeout is restored"): helper `install_default_timeout` in tests/rag/_netguard.py, used by tests/rag/conftest.py,
tests in tests/rag/test_network_guard.py::TestSocketDefaultTimeoutScoping.
Verify: the helper is what conftest uses (no second code path); the test fails if the restore finalizer is removed (mutation in /tmp copy);
the full suite passes (use /tmp/h8-venv/bin/python -m pytest tests/rag -q). Also confirm the trailing-newline note is fixed.
Write .agents/deepseek/VERDICT-rag-eval-harness-round10b.md between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line evidence, counts, mutation result.
