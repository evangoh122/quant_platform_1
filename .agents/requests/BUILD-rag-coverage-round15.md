# BUILD-rag-coverage round 15 — IMPLEMENT NOW (DeepSeek CHANGES_REQUESTED on r14, test-only)

You are MiMo. Fix `.agents/deepseek/VERDICT-rag-coverage-round14.md`. Commit, LF endings, do not touch `.agents/dispatch.sh`,
never delete/weaken tests, mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`. Production code is correct — tests only.

Add value-leak tests on BOTH success paths of `_resolve_user_agent`: (a) SDK `secrets.get_secret` success (spec'd SecretsAPI mock,
base64 value) and (b) dbutils success (`databricks.sdk.runtime` dbutils and globals dbutils). Each runs with `caplog` at DEBUG and
captured stdout/stderr and asserts the seeded fake value never appears. Mutation proof (record in verdict): add
`logger.info("... value=%s", decoded)` at the SDK success log line (pipelines/sec_rag_ingest.py:~142) and the dbutils success line →
each new test FAILS. Run: python3 -m pytest tests/rag tests/bronze -q. Verdict: .agents/mimo/VERDICT-rag-coverage-round15.md.
