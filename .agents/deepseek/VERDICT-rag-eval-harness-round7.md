# Checker verdict: RAG eval harness round 7 (aa9ac2d)

Checker: Claude Sonnet subagent (DeepSeek out of credit)

## Verdict: CHANGES_REQUESTED

Tests: `tests/rag` 393 passed / 19 skipped (normal), 393 passed / 19 skipped (pyspark hidden).
pandas-3 venv lacks pydantic, so it could not collect (environment, not a code finding).
No tests deleted or weakened (diff 3135dcc..aa9ac2d is additions plus one strengthened assertion).

## Blocking findings

1. **Network guard is broken for connect/connect_ex** (tests/rag/conftest.py, `_fail_socket_connect` ~L125 and
   `_fail_socket_connect_ex` ~L134). `host, port = address[0] if ... else (...)` unpacks `address[0]`
   (the host STRING) into two names. Every `socket.connect` / `connect_ex` therefore raises
   `ValueError: too many values to unpack` (or "not enough" for AF_UNIX str paths), for loopback,
   IPv6 and external alike. Proved in a /tmp copy: raw connect to 93.184.216.34, connect_ex to 8.8.8.8,
   loopback AF_INET, AF_INET6 `::1`, and AF_UNIX all fail with ValueError, not the guard's message and
   not an allow. External connects are only "blocked" by accident, loopback/AF_UNIX allowance does not
   work. urllib to example.com and getaddrinfo ARE blocked with the guard's error (getaddrinfo is fine).
   Also `_is_loopback(None)` / non-str hosts return False (passive getaddrinfo(None, ...) blocked).
2. **No network-guard test exists** (BUILD item 2 required: requests.get / raw connect raise the guard
   error, loopback works). grep of tests/rag finds none. That is why finding 1 went unnoticed.
3. **cli_args redaction misses nested containers** (evals/rag_eval/report.py:42-62). A report built with
   `{"lst": [Path("/tmp/a/b.jsonl"), "/home/jianj/q"], "d": {"p": Path("/home/jianj/z")}}` outputs those
   paths verbatim. Top-level Path, PathLike and absolute str ARE handled (`golden` -> `g.jsonl`).
   Current CLI args are flat, so the real CLI is not leaking today, but the requested behaviour is absent.
4. **No test through `cli.main` with real Path args** (BUILD item 1). The new test only calls
   `build_report` (tests/rag/test_rag_eval_report.py ~L206). No "PosixPath" Markdown assertion either.
5. **Production-wrapper parity test compares chunk ids only, not scores**
   (tests/rag/test_rag_eval_retrieval.py, `TestProductionWrapperMatchesHarness`). It does call real
   `tr.search_sec_filings` (good), but patches `normalize_symbol` and `HybridRetriever`, and the fake
   reranker is copy-pasted instead of using the new `fake_reranker` fixture (the `cached_offline_adapter`
   and `fake_reranker` fixtures in conftest.py are unused). Order-only for prod wrapper was what BUILD
   asked ("same chunk ids, same order"), so this is minor; scores compared in the retrieve_and_rerank vs
   retrieve_mode test (item 3 of the ask, satisfied there).

## Verified
- Rerank parity test compares `(chunk_id, rerank_score)` tuples (test_rag_eval_retrieval.py ~L406-415).
- Path redaction mutation (replace `_redact_path(v)` with `v`): both cli_args tests fail (2 failed).
- Network mutation (remove connect patch): not meaningful, since no test covers it (finding 2).
- Rerank score perturbation mutation: not run; both paths share one production function so a
  perturbation there affects both equally, the score test only catches path divergence.

## Required next round
Fix the unpack bug (use `address[0]` as host only when address is a tuple; handle str/bytes AF_UNIX as
allowed; handle None host), add guard tests (external urllib/requests/raw connect/connect_ex raise the
guard message; loopback TCP, ::1 and AF_UNIX work), recurse cli_args redaction through list/tuple/dict,
and add a `cli.main` test with real Path args asserting no absolute path and no "PosixPath" in JSON and
Markdown output.
