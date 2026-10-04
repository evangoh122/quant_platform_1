# BUILD: RAG eval harness round 7 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests.

Checker (`.agents/deepseek/VERDICT-rag-eval-harness-check3.md`): the shared composition, ordered
parity, no-text reports and PIT gate are VERIFIED. Two blocking issues:

1. **`cli_args` path redaction doesn't work on a real run.** `report.py:~39-46` only redacts `str`,
   but the CLI args are `pathlib.Path` (`cli.py:~96-104`). A real run wrote full `/home/jianj/...`
   paths, and the Markdown shows `PosixPath('/home/...')`.
   - Redact any `os.PathLike`, or any value whose `str()` looks like an absolute path, to its
     basename. Render paths as plain strings, never a repr.
   - Test THROUGH `cli.main` with real `Path` args: the default JSON and Markdown contain no
     absolute path and no "PosixPath".
2. **The network guard is bypassable.** Only `socket.create_connection` is patched; `requests.get`
   still connects.
   - Also patch `socket.socket.connect`, `socket.socket.connect_ex` and `socket.getaddrinfo`.
   - Allow only loopback (127.0.0.0/8, ::1) and AF_UNIX.
   - Test: in a test, `requests.get("https://example.com")` and a raw `socket.connect` to an external
     address both raise the guard's error, and loopback still works.

Also, from the non-blocking notes:
- Make the rerank parity test compare scores, not just order.
- Add one end-to-end test comparing the PRODUCTION `search_sec_filings` output with the harness
  `hybrid_rerank` output on the fixture: same chunk ids, same order.
- Keep parity tests fast: cache the fixture retriever per module, and use a fake reranker.

Run:
- `python3 -m pytest -q -p no:cacheprovider tests/rag`;
- the full suite with `--ignore=tests/lakebase`;
- both with pyspark hidden.

LF line endings only. Don't touch `.agents/dispatch.sh`. Write
`.agents/mimo/VERDICT-rag-eval-harness-round7.md`.
