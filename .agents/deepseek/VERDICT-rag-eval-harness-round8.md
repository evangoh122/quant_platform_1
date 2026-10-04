# VERDICT rag-eval-harness round 8
Checker: Claude Sonnet subagent (DeepSeek out of credit)
Verdict: CHANGES_REQUESTED

Tests (Linux, venv /tmp/h8-venv): `pytest tests/rag` = 413 passed, 19 skipped; same with pyspark hidden (PYTHONPATH nps) = 413 passed, 19 skipped.
tests/rag/test_network_guard.py: 11 passed, 0 skipped on Linux (AF_UNIX tests run).

## Findings
1. BLOCKING (item 5 not done). tests/rag/test_rag_eval_retrieval.py:189-262 `TestProductionWrapperMatchesHarness` still compares chunk ids only
   (`harness_chunk_ids == prod_chunk_ids`, L254-262). The request required (chunk_id, score) tuples like the harness parity test.
   MiMo only deleted the unused `cached_offline_adapter` / `fake_reranker` fixtures (OK, but that is the "or delete" half only).
   Fix: compare `(chunk_id, score)` for harness docs vs prod results (score field as exposed by search_sec_filings).
2. Minor (weakened assertion). tests/rag/test_rag_eval_report.py:~221 changed
   `== "relative/corpus.jsonl"` to `Path(...) == Path(...)`. Harmless on Linux but loosens the exact-string check; restore the exact string
   (the Windows separator issue should be handled in report.py, not the test), or justify.
3. Minor (coverage gap). Dict-KEY redaction (report.py `_redact_recursive`, dict branch) has no test; no test passes a path as a dict key.
   Request item 3 said "dict keys too". Add `{"m": {"/home/x/k.jsonl": 1}}` test.
4. Minor. conftest.py:~91 `_is_loopback` accepts any 4-part host starting with "127" (e.g. "127.1.evil.com"); not numerically validated. Low risk, test-only guard.
5. Note. tests/rag/test_guard_mutation_proofs.py is a script (collects 0 tests), not a test; fine as documentation.
6. Item 4 e2e test passes `str(...)` args to cli.main (cli converts to Path); acceptable. It checks "/home", str(tmp_path), "PosixPath" in both JSON and MD (test_rag_eval_report.py TestCliEndToEndReport).

## Verified OK
1. conftest.py guard (~L104-160): AF_INET (host,port) and AF_INET6 via address[0],[1]; AF_UNIX always allowed before unpacking (`self.family == AF_UNIX`); loopback 127/8, ::1, localhost allowed; others raise ConnectionRefusedError("Network access blocked in tests ..."); getaddrinfo(None) allowed (host is None); non-loopback hostname blocked at getaddrinfo and create_connection.
2. test_network_guard.py asserts `pytest.raises(ConnectionRefusedError, match="Network access blocked in tests")`; loopback tests do real bind/listen/connect (v4, localhost, ::1 ran, create_connection); AF_UNIX socketpair + connect run on Linux.
3. report.py recursion over dict (keys+values), list/tuple/set; tests TestRecursiveRedaction incl. `{"a":[Path("/home/x/y.jsonl"),"/tmp/a/b.jsonl"]}`.
6. `git diff 52953c6..HEAD -- tests`: only removed lines are the two buggy `address[0]` lines, the two unused fixtures, and the relative-path assertion (finding 2). No tests deleted.

## Mutation proofs (/tmp/h8-mut-1..4, copies; results)
- M1 remove `socket.socket.connect` patch: 1 failed (test_socket_connect_blocked), 10 passed. (Without per-test timeout the run hangs on the real connect.)
- M2 reintroduce `host, port = address[0]` in connect/connect_ex: 6 failed (incl. test_loopback_connect, test_loopback_create_connection, test_localhost_connect, test_ipv6_loopback_connect, connect_ex_blocked), 5 passed.
- M3 recursion skips list/tuple: 6 failed in test_rag_eval_report.py (TestRecursiveRedaction incl. test_nested_list_in_dict_redacted).
- M4 bypass redaction (`report["cli_args"] = _redact_recursive(...)` -> pass): TestCliEndToEndReport::test_report_no_path_leaks fails.

Required before APPROVED: finding 1 (and ideally 2, 3).
