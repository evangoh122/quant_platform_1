# VERDICT rag-eval-harness round 9 (af6e5c8..HEAD)
Checker: Claude Sonnet subagent (DeepSeek out of credit)
Verdict: CHANGES_REQUESTED

## Counts (Linux, /tmp/h8-venv)
- `python -m pytest tests/rag -q`: 418 passed, 19 skipped, 0 failed (MiMo's "2 failed" does NOT reproduce on Linux).
- Same with pyspark hidden (PYTHONPATH=.../scratchpad/nps): 418 passed, 19 skipped.
- tests diff af6e5c8..HEAD: no test deleted or weakened. Removed lines are only the old `_is_loopback`, the chunk-id-only assertion (replaced by a stronger one), a comment, and call_log scaffolding.

## Findings
1. BLOCKING (item 1 only half-met). tests/rag/test_rag_eval_retrieval.py:~254-277: `prod_seq = list(_prod_reranked_docs)` is captured INSIDE the fake reranker (L~217-224), not from the production wrapper's return value. `search_sec_filings` (agent/tools_retrieval.py:67-110) returns no rerank_score at all (only similarity/distance). So the (chunk_id, score) comparison is harness-vs-reranker-capture, not harness-vs-production-output.
   Mutation M-a (/tmp/h9-mut-1, scale d.metadata rerank_score/similarity x1.01 in wrapper before building output): test FAILS, but only by accident (the doc objects are shared/aliased, so harness metadata changes after the prod run).
   Mutation M-b (/tmp/h9-mut-2, perturb only the wrapper's OUTPUT dict: similarity*1.01+0.5 and add rerank_score*1.01): test PASSES (3 passed). The request's "perturb the score in the production wrapper only -> FAILS" is not truly satisfied. Fix: assert on results_prod values (compare r["similarity"] etc. against the harness doc metadata), or expose rerank_score in the output and compare it.
2. MAJOR (item 5). pytest-timeout is NOT in requirements.txt and NOT in .github/workflows/ci.yml:44 (pip install pytest pytest-asyncio httpx ...). It is installed only in /tmp/h8-venv. In CI, pytest.ini `timeout = 30` yields only a PytestConfigWarning "Unknown config option: timeout" (no error; `-W error`/--strict-config not used), so the timeout silently does nothing. Verified with `-p no:timeout`: 15 passed, 1 warning. Add pytest-timeout to CI install/requirements-dev.
3. MAJOR (item 5). tests/rag/conftest.py:88 `socket.setdefaulttimeout(10)` is in an autouse fixture (74) and is never restored (no monkeypatch/finalizer). It leaks as process-global state to every later test (tests outside tests/rag, in the same session) and after the session. Use monkeypatch-style restore (`old = socket.getdefaulttimeout(); yield; socket.setdefaulttimeout(old)`).
4. MAJOR (item 4, tautological tests). tests/rag/test_network_guard.py TestIsLoopbackValidation: three tests (127.0.0.2, ::1, 127.1.evil.com) re-define a local copy of `_is_loopback` and test the copy, not conftest (unused `_block_network` import too). Mutation M-c (/tmp/h9-mut-3, conftest `_is_loopback` -> `host in ('127.0.0.1','::1')`, so 127.0.0.2 blocked): 15 passed, mutation SURVIVES. Only `test_guard_blocks_127_subdomain` exercises the real guard; mutation M-d (old behaviour, startswith("127")) is killed by it (1 failed, 14 passed). Fix: test 127.0.0.2/::1 allowed through the real guard (bind/connect or call the actual function).
5. Item 4 production code OK: conftest.py:~90-103 uses ipaddress; "localhost" allowed, ValueError -> blocked.
6. Item 2 OK: test_rag_eval_report.py:222 asserts `== "relative/corpus.jsonl"` plus Path check; report.py:64,74 normalizes backslashes.
7. Item 3 OK: test_rag_eval_report.py `test_dict_keys_redacted_to_basename` (Path and str keys -> k.jsonl, b). Mutation M-e (/tmp/h9-mut-5, key redaction removed in report.py:84): 1 failed (that test), 26 passed.

## Required before APPROVED
Findings 1-4.
