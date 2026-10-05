# BUILD-xbrl-B1a round 6 (Codex round-2 CHANGES_REQUESTED — one finding)

You are MiMo. Branch `feat/xbrl-fundamentals` (stay on it). Read `.agents/codex/VERDICT-xbrl-B1a-r2.md`. LF endings, never touch
`.agents/dispatch.sh`, no Databricks, no network. Shell rule: if a command needs quoting, write it to
`/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run exactly `wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`.
No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp. COMMIT; verdict `.agents/mimo/VERDICT-xbrl-B1a-r6.md`.
pipelines/sec_rag_ingest.py:847-890 — when retries are exhausted for 403/429/5xx, raise SecClientError WITH `status_code` = the last response
status (and keep the attempt count). pipelines/ingest_sec_companyfacts.py:504-506 — the manifest records that http_status and an error
category matching it (e.g. "rate_limited" for 429, "forbidden" for 403, "server_error" for 5xx — not "client_error").
Tests (fake HTTP, fake clock): 403 x5 → manifest http_status=403, attempts=5, category forbidden; 429 x5 → 429; 503 x5 → 503. Paste FAILED output
with `status_code` dropped from the exhausted-retry error (revert in a `git archive HEAD | tar -x -C /tmp/<dir>` copy). Keep sec_rag_ingest.py
edits minimal and local (it is shared with PR #28).
