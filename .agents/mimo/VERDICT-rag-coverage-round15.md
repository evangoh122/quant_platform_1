# VERDICT: rag-coverage round 15 — MiMo
**Status:** APPROVED
**Round:** 15

## Blocking findings
None.

## Non-blocking notes
- `.agents/dispatch.sh` shows a mode change (100755→100644) in `git diff HEAD` due to Windows filesystem not preserving Unix permissions. Pre-existing, not caused by this round. Not committed.
- 9 test modules fail to collect due to missing dependencies (`loguru`, `polars`, `langchain_core`) — pre-existing environment issue, not related to this round's changes.

## What was done (test-only, no production changes)

Three value-leak tests added to `TestResolveUserAgent` in `tests/rag/test_sec_rag_ingest.py`, covering ALL three success paths of `_resolve_user_agent`:

1. **`test_sdk_success_value_never_in_logs`** — SDK `get_secret` + base64 decode path. Mocks `WorkspaceClient` with `MagicMock(spec=SecretsAPI)`, seeds `GetSecretResponse` with base64-encoded value, asserts decoded value absent from every `caplog` record, `caplog.text`, captured stdout, and stderr.

2. **`test_dbutils_sdk_runtime_success_value_never_in_logs`** — `databricks.sdk.runtime` dbutils path. Mocks `sdk_runtime.dbutils.secrets.get()` returning a known value, asserts value absent from logs/stdout/stderr.

3. **`test_dbutils_globals_success_value_never_in_logs`** — `globals().get("dbutils")` path. Sets `MagicMock(dbutils=None)` on sdk_runtime to fall through, injects `dbutils` into the pipeline module's globals, asserts value absent from logs/stdout/stderr.

Each test runs with `caplog.at_level("DEBUG")` and `capsys.readouterr()`.

## Mutation proof (all 3 FAIL as expected)

Mutation applied: `logger.info("DEBUG_MUATION value=%s", <secret>)` added after each success-path log line.

| Mutation site | Test that FAILs | Confirmed |
|:---|:---|:---|
| `sec_rag_ingest.py:~142` (SDK decoded) | `test_sdk_success_value_never_in_logs` | FAIL — value in caplog |
| `sec_rag_ingest.py:~114` (sdk_runtime) | `test_dbutils_sdk_runtime_success_value_never_in_logs` | FAIL — value in caplog |
| `sec_rag_ingest.py:~127` (globals dbutils) | `test_dbutils_globals_success_value_never_in_logs` | FAIL — value in caplog |

All mutations reverted; production code unchanged.

## Checks run

- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q -k "ResolveUserAgent or ValidateUserAgent or JobsYml or RunIngestUserAgent"` → **25 passed** (was 22 in r14, +3 new)
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q -k "test_sdk_success_value_never_in_logs or test_dbutils_sdk_runtime_success_value_never_in_logs or test_dbutils_globals_success_value_never_in_logs"` → **3 passed**
- Mutation: SDK path → `test_sdk_success_value_never_in_logs` → **FAILED** (value leaked in log record)
- Mutation: sdk_runtime path → `test_dbutils_sdk_runtime_success_value_never_in_logs` → **FAILED** (value leaked in log record)
- Mutation: globals path → `test_dbutils_globals_success_value_never_in_logs` → **FAILED** (value leaked in log record)
- `git diff HEAD -- pipelines/` → **empty** (no production code changes)
- `rg "DEBUG_MUATION" pipelines/` → **0 matches** (mutations reverted)
- LF endings confirmed (no CRLF in test file)
- Committed: `bf6e74f` on `slice/rag-coverage`