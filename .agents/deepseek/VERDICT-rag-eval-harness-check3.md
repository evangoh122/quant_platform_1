Checker: Claude Sonnet subagent (DeepSeek out of credit)

===VERDICT START===

**Status:** CHANGES_REQUESTED

## Blocking findings

1. **cli_args absolute-path redaction does not work on real CLI runs.**
   `evals/rag_eval/report.py:39-46` redacts only values where `isinstance(v, str)`. The CLI declares
   `--golden/--corpus/--embeddings/--output-dir` with `type=Path` (`cli.py:96-104`) and stores
   `vars(args)` (`cli.py:276`), so the values are `PosixPath` objects and are skipped.
   Proof: real run `python -m evals.rag_eval --adapter jsonl --golden .../golden_smoke.jsonl ...`
   wrote `/home/jianj/code/qp1-eval-harness/tests/...` full absolute paths into the default JSON
   `cli_args` (json `default=str`), and the Markdown prints `PosixPath('/home/jianj/...')` (`report.py:92`).
   The unit test (`test_rag_eval_report.py:190`) passes only because it feeds plain `str`.
   Fix: redact `os.PathLike` too (e.g. `isinstance(v, (str, os.PathLike)) and Path(v).is_absolute()`
   -> `Path(v).name`), also for list values (e.g. `mode`), and add a test through `cli.main` (or with `Path` objects)
   asserting no `/home` or `/tmp` substring in the JSON or Markdown report.

2. **The network guard is bypassable and does not "really" block network.**
   `tests/rag/conftest.py` `_block_network` patches only `socket.create_connection`.
   Proof (copy of the conftest plus a probe test): `socket.create_connection` is blocked, but
   `requests.get("https://example.com")` inside the same autouse context did NOT raise (urllib3 opens
   its own `socket.socket().connect`). httpx/huggingface_hub-style clients can bypass it the same way.
   Fix: also patch `socket.socket.connect` / `connect_ex` (allow AF_UNIX and loopback only) and
   `socket.getaddrinfo` for non-loopback hosts; add a probe test asserting `requests.get` and
   `urllib.request.urlopen` raise.
   Mitigating: with a hard connect-block shim, `tests/rag` made zero connections on 3 repeat runs (a first cold run
   logged 3 :443 connect attempts that did not reproduce), and no test calls
   SentenceTransformer/CrossEncoder/from_pretrained for real. So no test is currently proven to hit the
   network, but the guard itself is weaker than claimed.

## Non-blocking notes

- Shared composition: PASS. `search_sec_filings` (`agent/tools_retrieval.py:93`) and
  `retrieve_mode("hybrid_rerank")` (`hybrid_retriever.py:790`) both call `HybridRetriever.retrieve_and_rerank`
  (`:683`); `hybrid_rrf` mode calls `retrieve()` directly. The harness `retrieve_item` goes through `retrieve_mode`.
- The "production tool vs harness" parity is structural (mock asserts `search_sec_filings` calls
  `retrieve_and_rerank`; ordered parity test compares `retrieve_and_rerank()` vs `retrieve_mode`). It is not an
  end-to-end tool-output vs harness comparison. Because both paths share one function, a mutation INSIDE
  `retrieve_and_rerank` is not caught by the parity test (only by the call-count/mock tests). Acceptable.
- Rerank parity compares chunk_id order only, not `(chunk_id, score)`; the RRF test compares
  `(chunk_id, component_score)`. Request said scores for both; strengthen the rerank test to include `rerank_score`.
- Mutation M4 (production tool calling `retrieve()` instead of `retrieve_and_rerank`) hit my 300s cap, so it is
  not verified; the mock-based tests would fail it by `assert_called_once` on `retrieve_and_rerank`.
- Each parity test takes about 47-94s cold (torch import) in a fresh copy; warm `tests/rag` takes about 7s.
- `--include-text` JSON: truncated to max 138 chars here (fixture chunks are shorter than 200); the
  Markdown report never contains text even with the flag. Fine.

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/rag`: 391 passed, 19 skipped (about 31s cold, 7s warm).
- Full suite `--ignore=tests/lakebase`: 660 passed, 77 skipped (422s).
- `tests/rag` with pyspark/databricks hidden via sitecustomize (sys.modules entries = None): 391 passed, 19 skipped.
  The full suite with pyspark hidden was also run (log in scratch); the final line was likewise 660 passed, 77 skipped.
- Mutations in a `git archive` copy (scratch): baseline 2 pass; skip rerank in `hybrid_rerank` mode -> rerank
  parity test FAILS; reverse order in `hybrid_rerank` -> FAILS; reverse order in `hybrid_rrf` -> RRF parity test FAILS.
- Real CLI smoke run, default: no fixture sentence (e.g. "record revenue of 60.9") in JSON or Markdown; hit keys are
  accepted_ts, accession, chunk_id, component_score, distance, form_type, rank, rerank_score, retrieval_mode,
  section, similarity, ticker (no `text`/`chunk_text`). `--include-text`: `text` present, max length 138 (<=200), JSON only.
  cli_args paths NOT redacted (finding 1).
- End-to-end through `cli.main` with a patched module: clean -> exit 0, PASS, leakage 0; identity `_pit_filter` ->
  exit 1, FAIL, leakage 5 (all `smoke-005-future`); injected `bm25_search` error -> exit 1, INCOMPLETE, leakage 0.
- Hand calc vs `metrics.py`: recall@5 = 2/3, MRR = 1/2, nDCG@5 = 0.70392 (DCG/IDCG by hand) all match.
- Network: hard `socket.socket.connect` shim over `tests/rag` -> no connection attempts in 3 runs (one cold run saw 3);
  probe test: `create_connection` blocked, `requests.get` not blocked (finding 2).

===VERDICT END===
