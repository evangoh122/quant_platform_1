# CHECK: XBRL B1a round 3 — Codex findings (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies. Run WSL commands directly (`wsl -d Ubuntu -- bash -lc '<cmd>'`),
never via PowerShell wrappers or C:\temp scripts. Write .agents/deepseek/VERDICT-xbrl-B1a-r3.md between ===VERDICT START=== /
===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Findings to verify fixed: .agents/codex/VERDICT-xbrl-B1a.md (4 blocking + 4 non-blocking). Spec .agents/requests/BUILD-xbrl-B1a-r3.md.
Commits 6d4413c, c2ba54a. MiMo's verdict is a self-report. Claude: 255 passed (companyfacts + sec_rag_ingest tests).
Claude spotted, please confirm and judge:
- pipelines/sec_rag_ingest.py `_validate_user_agent` error message includes `repr(user_agent)` — that leaks the contact email into exceptions/logs
  (Plan §2.1: never log contact data). Blocking if confirmed.
- attempt_count = `client.request_count - req_before` on a SHARED client under a ThreadPoolExecutor — concurrent fetches contaminate each other's
  count (Codex's non-blocking item not actually fixed).
Mutations, each must fail a test: 403 not retried; seen_payloads marked before the write; old UA validation (accepts "foo"); http_status removed.
Also: UA regex accepts realistic values ("quant-platform research evangohsg@gmail.com", "MyApp/2.0 contact@company.com") and rejects "foo",
"foo bar", "a@b.com" alone, "Sample Company Name AdminContact@<sample company domain>.com". Offline suite green.
