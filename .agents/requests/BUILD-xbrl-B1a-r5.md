# BUILD-xbrl-B1a round 5 (DeepSeek CHANGES_REQUESTED on r4 — two tests are not mutation-proof)

You are MiMo. Branch `feat/xbrl-fundamentals` (stay on it). Read `.agents/deepseek/VERDICT-xbrl-B1a-r4.md`. LF endings, never touch
`.agents/dispatch.sh`, no Databricks, no network.
Shell rule: if a command needs quoting, write it to `/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run exactly
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`. No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp.
Tests only; do not change production code unless a test proves it wrong. COMMIT; verdict `.agents/mimo/VERDICT-xbrl-B1a-r5.md`.
1. `test_concurrent_attempt_count_per_cik` must really overlap: use a threading.Barrier (or Events) in the fake HTTP client so CIK A's
   retries happen WHILE CIK B's request is in flight (e.g. A: 429,429,200; B: 200 released only after A's first attempt), and assert A's manifest
   attempt_count == 3 and B's == 1. Show FAILED output with the shared-counter version restored
   (`attempt_count = client.request_count - req_before` at the call site and both except blocks) — revert in a
   `git archive HEAD | tar -x -C /tmp/<dir>` copy, not in the worktree.
2. Duplicate-manifest attempt_count: a fixture where the duplicate payload's fetch needed retries (e.g. 429 then 200), assert the
   skipped_duplicate manifest row carries that attempt_count (2), not the default 1. Show FAILED output with
   `manifest.attempt_count = attempt_count` removed from the skipped_duplicate branch.
