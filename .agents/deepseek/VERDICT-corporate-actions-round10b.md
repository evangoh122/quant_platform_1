===VERDICT START===
# VERDICT: corporate-actions-round10b — DeepSeek (checker)
**Status: APPROVED**
**Round:** 10b
Scope: commit 314983d (Claude's fix — extract `_resolve_cli_api_key()` + `TestCliApiKeyResolution`). Re-check of the single round-10 blocker (CLI mode never base64-decoded the SDK secret). Read-only review; mutation proof in /tmp/corpact-mut copy.

## Verified OK — the round-10 blocker is fixed

### 1. SDK secret is base64-decoded in CLI mode.
`notebooks/refresh_bronze_corporate_actions.py:95-111` defines `_resolve_cli_api_key()`:
- `MASSIVE_API_KEY` env var → returned **verbatim** (plaintext, no decode). Lines 101-103.
- else SDK path `WorkspaceClient().secrets.get_secret("evangoh_capstone","massive_s3_secret_key").value` → `base64.b64decode(raw).decode("utf-8").strip()`. Line 111.
- `main()` line 518 now calls `_resolve_cli_api_key()`; the old inline SDK read (which returned `.value` undecoded) is deleted. `import base64` added at line 28.

### 2. Env-var and SDK branches are correctly distinguished.
`test_env_var_used_verbatim` asserts the env var is returned with no decode; `test_sdk_secret_is_base64_decoded` injects a fake `databricks.sdk` module whose `get_secret` returns a base64 blob and asserts `_resolve_cli_api_key() == "PLAINTEXT_KEY_123"`. Both pass. The fake-SDK test also asserts the exact scope/key tuple `("evangoh_capstone","massive_s3_secret_key")`, pinning the secret reference.

### 3. Mutation proof: returning the raw value breaks the regression test.
Copied HEAD via `git archive HEAD | tar -x -C /tmp/corpact-mut`, then changed line 111 from `return base64.b64decode(raw).decode("utf-8").strip()` to `return raw`. `test_sdk_secret_is_base64_decoded` **FAILS** (`assert 'UExBSU5URVhUX0tFWV8xMjM=' == 'PLAINTEXT_KEY_123'`). The test is load-bearing against the exact defect it guards.

### 4. Key never reaches logs/exceptions in the new helper.
`_resolve_cli_api_key()` contains no `print`/logging and returns the key directly to `main()`, where it is passed only into `_make_adapter(...)`. The SDK read is wrapped in `try/except Exception: return ""` — the exception is swallowed silently and `raw` is never embedded in any message. The base64 decode sits **outside** the try block; if it raises, the resulting `binascii.Error`/`UnicodeDecodeError` does not contain the secret value. Downstream adapter logging already redacts the key (`_redact_api_key` in both `etl/corporate_actions.py:210,233,246` and `notebooks/...:362,381`). No key leakage path.

## Blocking findings
None.

## Non-blocking notes
1. **[notebooks/refresh_bronze_corporate_actions.py:104-108] the SDK `except Exception` returns `""` with no diagnostic**, so a misconfigured SDK credential surfaces only as the generic `"Massive API key required"` RuntimeError at line 520. Acceptable (avoids leaking SDK error details), but slightly less debuggable.
2. **[notebooks/refresh_bronze_corporate_actions.py:111] base64 decode is outside the try block** and would raise uncaught if the SDK secret were ever stored non-base64 (or non-UTF-8). Correct per the SDK contract, but worth a defensive `try/except` in a later round if plaintext secrets could ever coexist.
3. Stray blank line at lines 93-94 (PEP8 nit); cosmetic only.

## Checks run
- `python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → **356 passed, 13 skipped, 0 failed** (25.24s)
- `python3 -m pytest -q tests/bronze/test_corporate_actions.py -k "CliApiKeyResolution"` → **2 passed, 0 failed**
- Mutation (return raw) in /tmp/corpact-mut → `test_sdk_secret_is_base64_decoded` → **FAIL** (proves the regression test guards the fix)
- Source review of `_resolve_cli_api_key` + `main()` call site → no logging/exception leakage of the key
===VERDICT END===
