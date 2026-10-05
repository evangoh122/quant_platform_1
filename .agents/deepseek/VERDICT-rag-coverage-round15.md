===VERDICT START===
# VERDICT: rag-coverage round 15 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 15

## Summary

The round-14 blocker is resolved. Commit `bf6e74f` (tests only) adds exactly three value-leak
mutation tests to `TestResolveUserAgent`, covering all three non-env success paths of
`_resolve_user_agent`:

| Test (file:line) | Path exercised | Production success line |
| :--- | :--- | :--- |
| `test_sdk_success_value_never_in_logs` (`tests/rag/test_sec_rag_ingest.py:3146`) | SDK `WorkspaceClient().secrets.get_secret` + base64 decode | `pipelines/sec_rag_ingest.py:142` |
| `test_dbutils_sdk_runtime_success_value_never_in_logs` (`:3195`) | `databricks.sdk.runtime` dbutils | `pipelines/sec_rag_ingest.py:113` |
| `test_dbutils_globals_success_value_never_in_logs` (`:3233`) | `globals().get("dbutils")` | `pipelines/sec_rag_ingest.py:126` |

Each test seeds a distinct secret value, runs `_resolve_user_agent()` under
`caplog.at_level("DEBUG", logger="pipelines.sec_rag_ingest")` + the `capsys` fixture, asserts the
resolved value matches (precondition that the intended path actually ran), then asserts the seeded
value is absent from every log record (`record.getMessage()`), `caplog.text`, `captured.out`, and
`captured.err`. The SDK test mocks the real API (`MagicMock(spec=SecretsAPI)` returning a
`GetSecretResponse(key=..., value=base64(...))`); the sdk_runtime test patches
`databricks.sdk.runtime` with `dbutils=mock_dbutils` (non-None); the globals test patches
`databricks.sdk.runtime` with `dbutils=None` and injects `mod.dbutils` so it falls through to the
`globals()` branch (with a `try/finally` restore).

## Mutation proof (re-run)

In a `git archive HEAD` copy at `/tmp/ragcov-mut15` I added the exact mutations the round
specifies — `logger.info("... value=%s", decoded)` after the SDK decode, and
`logger.info("... value=%s", secret_val)` after each of the two dbutils `secrets.get` calls —
and ran the three new tests:

```
$ python3 -m pytest tests/rag/test_sec_rag_ingest.py -q \
    -k 'sdk_success_value_never_in_logs or dbutils_sdk_runtime_success_value_never_in_logs or dbutils_globals_success_value_never_in_logs'
3 failed, 155 deselected in 2.59s
```

Each failure traces to its own path leaking its own seeded value:
- SDK  → `... value=LeakedAgent leak@company.com` (`sec_rag_ingest.py:144`, decoded value)
- sdk_runtime → `... value=RuntimeAgent runtime@company.com`
- globals → `... value=GlobalAgent global@company.com`

So the r14 blocker ("log the value → no test fails") is closed: adding a value log at any success
line now fails its dedicated test.

## Production code / rounds 10–14 intact

- `git diff 306a187..HEAD -- pipelines db services agent` → empty (no production change since the
  r14 fix). `git show bf6e74f --name-only` → only `tests/rag/test_sec_rag_ingest.py`; the diff is
  `134 insertions(+), 0 deletions(-)` (additive only, no test weakened/deleted).
- Full suite: `python3 -m pytest tests/rag tests/bronze -q` → **698 passed, 36 skipped, 0 failed**
  (r14 was 695 passed; +3 net new = the three value-leak tests). `TestResolveUserAgent` → 14 passed.

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` → **698 passed, 36 skipped** (22.1s).
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q -k "ResolveUserAgent or ValidateUserAgent or JobsYml or RunIngestUserAgent"` → **25 passed**.
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py::TestResolveUserAgent -q` → **14 passed**.
- Mutation (git archive copy, 3 value-log insertions) → `pytest -k "sdk_success_value_never_in_logs or dbutils_sdk_runtime_success_value_never_in_logs or dbutils_globals_success_value_never_in_logs"` → **3 failed**.
- `git diff 306a187..HEAD -- pipelines db services agent` → empty (no production change).

## Non-blocking notes

- The `bf6e74f` commit message says "TestResolveUserAgent: 25 passed (was 22 in r14)" — that 25 is
  the `-k "ResolveUserAgent or ValidateUserAgent or JobsYml or RunIngestUserAgent"` combined count
  across four classes; the `TestResolveUserAgent` class itself is 14 tests. Cosmetic only, not a
  defect.
===VERDICT END===
