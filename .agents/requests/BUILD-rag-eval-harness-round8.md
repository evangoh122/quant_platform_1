# BUILD rag-eval-harness round 8 (builder: MiMo; checker: Claude Sonnet subagent standing in for DeepSeek)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-eval-harness. Commit after each item.
NEVER delete or weaken existing tests.
Checker verdict: .agents/deepseek/VERDICT-rag-eval-harness-round7.md (CHANGES_REQUESTED).

## 1 (blocking). Network guard unpack bug
tests/rag/conftest.py `_fail_socket_connect` / `_fail_socket_connect_ex` (~L125, ~L134) do `host, port = address[0]`,
which unpacks the host STRING -> ValueError for every address. Fix: handle address by family —
AF_INET `(host, port)`, AF_INET6 `(host, port, flow, scope)`, AF_UNIX `str/bytes` path (always allow AF_UNIX).
Allow loopback (127.0.0.0/8, ::1, "localhost"); block everything else with the guard's own error type/message.
`getaddrinfo(None, ...)` (passive) must be allowed.

## 2 (blocking). Guard tests
Add tests in tests/rag (they run under the guard):
- raw `socket.create_connection(("93.184.216.34", 80))`, `socket.socket().connect(("93.184.216.34",80))`,
  `connect_ex`, and `socket.getaddrinfo("example.com", 80)` each raise the GUARD's error (assert type + message, not just any exception).
- loopback works: start a listening socket on 127.0.0.1 (port 0) and connect to it successfully; same for ::1 if IPv6 is available (skip otherwise).
- AF_UNIX socketpair / connect to a temp unix socket works.
Mutation proofs (in /tmp copies, report output): remove the connect patch -> a test fails; reintroduce `address[0]` unpack -> loopback test fails.

## 3. Recursive redaction
evals/rag_eval/report.py:42-62: recurse into list/tuple/set/dict values (dict keys too if str/PathLike); same rules
(absolute -> basename, PathLike -> str). Test nested cases incl. `{"a": [Path("/home/x/y.jsonl"), "/tmp/a/b.jsonl"]}`.

## 4. cli.main end-to-end report test
Drive `evals/rag_eval/cli.main` (offline adapter, tmp_path output) with real absolute Path args; assert the JSON and
Markdown reports contain no "/home", no str(tmp_path), and no "PosixPath".

## 5. Minor
Production parity test: compare (chunk_id, score) like the harness parity test; use or delete the unused
`cached_offline_adapter` / `fake_reranker` fixtures.

## Acceptance
- python -m pytest tests/rag -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) all pass.
- .agents/mimo/VERDICT-rag-eval-harness-round8.md with counts + mutation-proof outputs. Commit everything.
