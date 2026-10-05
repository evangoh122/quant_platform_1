# RE-REVIEW 6: SEC RAG coverage after rounds 13–15 (reviewer: Codex gpt-5.6-sol)

You APPROVED r5 (.agents/codex/VERDICT-rag-coverage-r5.md). Claude's final review then found a deploy blocker: the Databricks
`sec_rag_ingest` job could never start — `SEC_EDGAR_USER_AGENT` was required but never provided to the serverless job. Fix rounds:
13 (865c642: resolve from env or Databricks secret, jobs.yml params), 14 (306a187: real `secrets.get_secret` + base64, dbutils detection
for serverless, spec'd SecretsAPI mocks), 15 (bf6e74f: value-leak tests on success paths). DeepSeek: r13 CHANGES_REQUESTED → r14
CHANGES_REQUESTED → r15 APPROVED. The secret `evangoh_capstone/sec_edgar_user_agent` exists in the workspace (do not try to read it).
Claude verified live from WSL with the env var unset that `_resolve_user_agent()` resolves the workspace secret correctly.
Do NOT edit repo files; mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Review the resolution chain end-to-end for a serverless spark_python_task (what actually runs there: databricks.sdk.runtime dbutils,
globals, SDK default auth inside a job), error clarity, no secret leakage (logs, exceptions, job output), jobs.yml parameters/argparse,
runbook. Re-confirm your r3–r5 verified items still hold. Last gate before the unattended rollout (dry-run → 10 → 50 → 300 → 557).
Print verdict between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line.
Run: python3 -m pytest tests/rag tests/bronze -q
