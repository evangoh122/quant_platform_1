# BUILD-xbrl-B1a round 4 (DeepSeek CHANGES_REQUESTED on r3)

You are MiMo. Branch `feat/xbrl-fundamentals` (stay on it). Read `.agents/deepseek/VERDICT-xbrl-B1a-r3.md`. LF endings, never touch
`.agents/dispatch.sh`, no Databricks, no network. Run WSL commands directly (`wsl -d Ubuntu -- bash -lc '<cmd>'`); never wrap wsl.exe in
PowerShell and never write scripts to C:\temp. COMMIT per item; verdict `.agents/mimo/VERDICT-xbrl-B1a-r4.md` — report honestly what is done.
Blocking:
1. pipelines/sec_rag_ingest.py `_validate_user_agent`: error messages must NOT include the User-Agent value (no repr/str/f-string of it).
   Say only what is wrong ("must be '<application name> <contact email>'"). Test: the raised message for a bad UA containing
   "someone@example.com" does not contain "@" or the input. Mutation: put repr(user_agent) back → FAIL.
2. The "seen_payloads marked before the write" mutation must fail a test: make `test_first_write_failure_allows_second_write` (or a new test)
   actually exercise ordering — first write raises, the identical payload is fetched again in the same run, assert it IS written. Paste
   FAILED output with `seen_payloads.add(...)` moved before the write.
Non-blocking (do them — they were asked for last round and not done):
3. attempt_count per CIK: have the fetch call return its own attempt count (or use a per-call counter), not `client.request_count` deltas on a
   shared client. Test with two concurrent fetches where one retries twice: each manifest row has its own count.
4. Duplicate manifests carry the computed attempt_count.
5. Concurrency test asserts peak concurrent fetches <= 4.
