# BUILD-xbrl-B1a round 3 (Codex CHANGES_REQUESTED)

You are MiMo. Branch `feat/xbrl-fundamentals` (stay on it). Read `.agents/codex/VERDICT-xbrl-B1a.md`. LF endings, never touch
`.agents/dispatch.sh`, no Databricks, no network in tests. Run WSL commands directly (`wsl -d Ubuntu -- bash -lc '<cmd>'`); never wrap wsl.exe in
PowerShell and never write scripts to C:\temp. COMMIT per item; verdict `.agents/mimo/VERDICT-xbrl-B1a-r3.md` with FAILED output per mutation.
Note: pipelines/sec_rag_ingest.py is shared with PR #28 (being edited on slice/rag-coverage). Keep changes there minimal and local to the lines
named below so the branches merge cleanly.
Blocking:
1. sec_rag_ingest.py:830-862 — retry HTTP 403 with the same bounded exponential backoff as 429 (honour Retry-After; capped attempts), then fail.
   Test: 403,403,200 → succeeds after 3 attempts; 403 x (max+1) → fails with attempts == max. Mutation: 403 not retried → FAIL.
2. ingest_sec_companyfacts.py:451-480 — add (cik, payload_hash) to `seen_payloads` only AFTER the Delta write succeeds (guard with a lock under
   concurrency). Test: first write raises → the identical second payload is written (not skipped). Mutation: mark before write → FAIL.
3. sec_rag_ingest.py:156-176 — UA must match `<application or company name> <contact email>` (a non-empty name token AND a valid-looking
   email); reject "foo", "foo bar", "a@b" without a name, placeholders. Tests for accept/reject cases. Mutation: old validation → FAIL.
4. Manifest gets `http_status` (int, last response status per CIK; null if no response). Schema/DDL + test.
Non-blocking (do them): per-CIK attempt_count (thread-local or returned from the fetch call, not a shared counter); duplicate manifests carry
the computed attempt_count; the concurrency test asserts max_workers <= 4 (e.g. peak concurrent fetches observed <= 4).
Acceptance: tests/bronze/test_sec_companyfacts.py, tests/rag/test_sec_rag_ingest.py and the offline suite green.
