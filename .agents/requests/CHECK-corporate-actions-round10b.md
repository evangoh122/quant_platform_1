# CHECK: corporate-actions round 10b (checker: DeepSeek) — re-check one fix

Read-only. Your round-10 blocker: CLI mode didn't base64-decode the SDK secret. Claude extracted `_resolve_cli_api_key()` in
notebooks/refresh_bronze_corporate_actions.py (env var plaintext; SDK value base64-decoded) + tests TestCliApiKeyResolution (latest commit).
Verify; mutation (copy via `git archive HEAD | tar -x -C /tmp/<dir>`): return the raw SDK value → test_sdk_secret_is_base64_decoded FAILS.
Confirm the key never reaches logs/exceptions in the new helper. Full suite: python3 -m pytest -q tests/bronze tests/silver tests/test_security.py.
Write .agents/deepseek/VERDICT-corporate-actions-round10b.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
