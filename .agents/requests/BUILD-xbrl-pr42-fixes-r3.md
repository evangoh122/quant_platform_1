# BUILD: PR #42 fixes round 3 (Codex sol CHANGES_REQUESTED — race regression test missing)

You are MiMo. Branch `feat/xbrl-fundamentals` (stay on it). Read `.agents/codex/VERDICT-xbrl-pr42-fixes.md`. LF endings, never touch `.agents/dispatch.sh`, no Databricks, no network.
Shell rule as before (`/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` + `wsl -d Ubuntu -- bash <path>`; no PowerShell, nothing in C:\temp). Stage only files you change. COMMIT; verdict
`.agents/mimo/VERDICT-xbrl-pr42-fixes-r3.md` with the FAILED output. Tests may only call production code; never copy its logic.
pipelines/ingest_sec_companyfacts.py:615-655 reserves (cik, payload_hash) before the Delta append and releases it on failure — correct, but no test catches a regression. Add ONE deterministic
test: two workers fetch the identical (cik, payload_hash) concurrently through the production run (fake HTTP returns the same payload for both); the fake writer's append BLOCKS on a
threading.Event for the first caller; release it after the second worker has reached the reservation check; assert exactly ONE append happened and the second is recorded as skipped_duplicate.
Paste FAILED output with the reservation moved back after the append (mark-seen-after-append), in a /tmp `git archive` copy. Also keep: a failed first append releases the reservation so a
later identical payload is written (existing test) — confirm it still passes.
