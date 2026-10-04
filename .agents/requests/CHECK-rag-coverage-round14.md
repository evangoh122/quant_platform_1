# CHECK: RAG coverage round 14 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Write .agents/deepseek/VERDICT-rag-coverage-round14.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Request: .agents/requests/BUILD-rag-coverage-round14.md; your r13 verdict: .agents/deepseek/VERDICT-rag-coverage-round13.md.
Commit 306a187. MiMo's self-report is NOT evidence.
Claude's live check (WSL, real workspace, env var unset): `_resolve_user_agent()` resolved the workspace secret correctly.
Verify: (1) `secrets.get_secret` used, base64-decoded; no silent `except: pass` — failures log exception TYPE only, then a clear final
error. (2) dbutils detection works for serverless spark_python_task (`databricks.sdk.runtime`), then globals; no IPython user_ns.
(3) tests use spec'd/autospec'd SecretsAPI mocks so a wrong method name fails; run mutations: rename to get_secret_value; skip decode;
log the value; drop jobs.yml params → each FAILS. (4) value never in logs/stdout/exceptions. (5) rounds 10–13 intact.
Run: python3 -m pytest tests/rag tests/bronze -q.
