# CHECK: RAG coverage round 13 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Write .agents/deepseek/VERDICT-rag-coverage-round13.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Request: .agents/requests/BUILD-rag-coverage-round13.md. Commit 865c642. MiMo's self-report is NOT evidence.
Context: the secret `evangoh_capstone/sec_edgar_user_agent` now exists in the workspace (Claude set it; you cannot read it — do not try).
Verify: env wins over secret; secret path works on a Databricks cluster (dbutils) AND via SDK where `.value` is base64 and decoded;
missing both → clear error naming scope/key; placeholder rejected; the value never reaches logs/stdout/exceptions (seeded fake value);
resources/jobs.yml passes the scope/key params to the sec_rag_ingest task and argparse accepts them; runbook documents secret creation
without a real value. Mutations: skip base64 decode → FAIL; log the value → FAIL; drop the jobs.yml params → FAIL.
Also confirm nothing from rounds 10–12 regressed. Run: python3 -m pytest tests/rag tests/bronze -q.
