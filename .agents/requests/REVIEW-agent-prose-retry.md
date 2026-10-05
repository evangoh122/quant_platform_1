# REVIEW: agent plain-prose answers + one corrective retry (reviewer: Codex)

Branch `fix/agent-prose-retry` = origin/main + 867568c (prose final answers) + 8632658 (one corrective retry). DeepSeek APPROVED:
.agents/deepseek/VERDICT-agent-prose-retry.md (4 mutations, all killed). Review agent/runtime.py, agent/model_client.py,
tests/agent/test_runtime.py. Run `python3 -m pytest tests/agent tests/api -q` yourself. Do mutation proofs only in /tmp copies made with
`git archive HEAD | tar -x -C /tmp/<dir>`. Decide on DeepSeek's three non-blocking notes (brace-free tool-call text accepted as prose;
no audit entry for the retried rejection; exception type name fed back to the model) — say whether any must be fixed before merge.
Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or "Status: CHANGES_REQUESTED"
and file:line evidence. Do not edit files.
