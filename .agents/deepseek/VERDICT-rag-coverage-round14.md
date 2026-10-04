===VERDICT START===
# VERDICT: rag-coverage round 14 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 14

## Summary

The round-13 blocker is fixed: `pipelines/sec_rag_ingest.py:139` now calls
`client.secrets.get_secret(scope=..., key=...)` (a real `SecretsAPI` method), base64-decodes
`.value` at `:141`, and every `except` at `:118/:131/:147` logs `type(exc).__name__` only (no
silent `except: pass`). dbutils detection at `:108-132` is serverless-correct
(`databricks.sdk.runtime` → `globals().get("dbutils")` → SDK; no IPython `user_ns`). The SDK
mocks are constrained to the real API (`MagicMock(spec=SecretsAPI)` at
`tests/rag/test_sec_rag_ingest.py:3020/3055`), so a wrong method name raises.

Three of the four required mutations fail as specified: rename `get_secret`→`get_secret_value`
(fails `test_sdk_base64_decode`, `test_sdk_base64_decode_mutation_skip_fails`,
`test_sdk_exception_logs_type_not_value`); skip base64 decode (fails 2 tests); drop jobs.yml
secret params (fails `test_sec_rag_ingest_task_passes_secret_params`). The fourth — "log the
value" — is **not** covered on the SDK success path (finding 1 below).

## Blocking findings

1. `tests/rag/test_sec_rag_ingest.py:3006` (and the dbutils success branches) — the "log the
   value" mutation required by BUILD round 14 item 3 ("log the value → FAIL") is not enforced on
   the SDK success path. The only value-leak tests exercise the **env** path
   (`test_value_never_appears_in_log` `:2989`, `test_log_value_leak_mutation_fails` `:3096`) and
   the SDK **exception** path (`test_sdk_exception_logs_type_not_value` `:3112`,
   `side_effect=RuntimeError`). None runs the SDK success path with `caplog` asserting the resolved
   value is absent.
   → Concrete failure scenario: edit `pipelines/sec_rag_ingest.py:142` to
   `logger.info("... (sdk) value=%s", decoded)`. I applied exactly this mutation in a
   `git archive HEAD` copy and ran `pytest tests/rag/test_sec_rag_ingest.py::TestResolveUserAgent -q`
   → **11 passed** (no test fails). The SEC User-Agent credential is then written to job logs with
   no failing test, violating CHECK item (4) "value never in logs/stdout/exceptions" and the
   explicit "log the value → FAIL" gate. The production code today is correct (only `secret_scope`
   and `type(exc).__name__` are logged), but the mutation protection is missing on the exact success
   path this round was opened to harden.

## Non-blocking notes

- `pipelines/sec_rag_ingest.py:108-132` — the two dbutils success branches
  (`sdk_runtime` and `globals`) also log only `secret_scope` and likewise have no value-leak
  mutation test. Lower risk than the SDK path (the round's focus), but the same one-line test
  pattern would cover them.
- `databricks.sdk.runtime` import at `:109` is intentionally unguarded-by-presence: outside
  Databricks it raises `ImportError`, which is caught and logged as a WARNING (`type(exc).__name__`),
  then falls through to `globals()`/SDK. Correct behaviour, verified.

## What is correct (verified)

- **get_secret + base64 decode**: `:139/:141` correct; `GetSecretResponse(key=..., value=base64(...))`
  mocks feed a real `.value`. Confirmed against installed `databricks-sdk` (`dir(SecretsAPI)` has
  `get_secret`, no `get_secret_value`).
- **no silent swallow**: all three `except` blocks log the exception TYPE then raise a clear final
  `ValueError("SEC_EDGAR_USER_AGENT not found … scope='…', key='…'")` at `:150-153`. No `except: pass`.
- **serverless dbutils detection**: `databricks.sdk.runtime` first (`:109`), then `globals().get("dbutils")`
  (`:122`); IPython `user_ns` lookup removed entirely.
- **mutation rename → FAIL**: `get_secret`→`get_secret_value` fails `test_sdk_base64_decode`,
  `test_sdk_base64_decode_mutation_skip_fails`, `test_sdk_exception_logs_type_not_value` (3 failed).
- **mutation skip decode → FAIL**: `decoded = resp.value` fails 2 tests (raw base64 returned).
- **mutation drop jobs.yml params → FAIL**: `test_sec_rag_ingest_task_passes_secret_params` fails.
- **rounds 10–13 intact**: full suite `python3 -m pytest tests/rag tests/bronze -q` → 695 passed,
  36 skipped, 0 failed (22.2s); `TestResolveUserAgent` etc. → 22 passed. +2 net new tests vs r13's 693.

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` (WSL, real workspace) → **695 passed, 36 skipped**.
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q -k "ResolveUserAgent or ValidateUserAgent or JobsYml or RunIngestUserAgent"` → **22 passed**.
- Mutation (git archive copy): rename `get_secret`→`get_secret_value` → `pytest -k "sdk_base64_decode or sdk_wrong_method_name or sdk_exception"` → **3 failed**.
- Mutation: skip base64 decode (`decoded = resp.value`) → `pytest -k "sdk_base64_decode"` → **2 failed**.
- Mutation: drop jobs.yml scope/key params → `pytest -k "JobsYml"` → **1 failed**.
- Mutation: log the value (`logger.info("... value=%s", decoded)`) → `pytest tests/rag/test_sec_rag_ingest.py::TestResolveUserAgent -q` → **11 passed (no failure)** ← blocking gap.

## Required fix

- Add a value-leak mutation test on the SDK success path (and ideally the two dbutils success
  branches): mock `get_secret` to return a real `GetSecretResponse`, call `_resolve_user_agent()`
  with `caplog`, and assert the decoded value is absent from every log record (and `caplog.text`).
  Then re-run `python3 -m pytest tests/rag tests/bronze -q`.
===VERDICT END===
