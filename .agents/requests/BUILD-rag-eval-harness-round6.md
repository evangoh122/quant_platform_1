# BUILD: RAG eval harness round 6, Codex review (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests (strengthening is fine).

Read `.agents/codex/VERDICT-rag-eval-harness.md`. Two blocking issues:

1. **Parity with the PRODUCTION path.** Production is `search_sec_filings` →
   `HybridRetriever.retrieve()` (BM25 + dense + RRF, at `hybrid_retriever.py:~607-681`) → the reranker
   applied in `agent/tools_retrieval.py`. `retrieve()` alone doesn't rerank.
   - Make the harness's `hybrid_rerank` mode call the SAME composition production uses: reuse one
     shared function, e.g. `retrieve_and_rerank()` in `hybrid_retriever.py`, called by both
     `search_sec_filings` and the harness.
   - `hybrid_rrf` must equal `retrieve()` exactly.
   - Parity tests compare ORDERED lists of `(chunk_id, score)`, not unordered sets: production
     tool output vs harness `hybrid_rerank`, and `retrieve()` vs harness `hybrid_rrf`. Use the
     fixture plus a deterministic fake reranker.
   - Mutation: reorder or skip rerank in one path → the test fails.
2. **Raw filing text in the reports.**
   - `RetrievalHit` text must NOT be serialised into report JSON or Markdown by default. Keep only
     `chunk_id`, accession, section, ticker, `accepted_ts`, rank and score.
   - Add `--include-text` (default off) for local debugging. Even then, truncate to 200 chars and
     never write text into the public scorecard artifact.
   - Test: the default report JSON contains no `chunk_text` / `text` field, and no sentence from
     the fixture corpus (search for a sample string).
   - Also record `cli_args` with absolute paths redacted to their basename.

Also, Codex's sandbox saw `tests/rag` stall at about 72%. Check whether any test does real network
or model downloads (e.g. a cross-encoder or HF model load) without a fake. Every test must be
offline and finish quickly. Add an autouse guard that makes network access fail fast in tests (e.g.
monkeypatch `socket.create_connection` to raise), and fix any test it catches.

Run:
- `python3 -m pytest -q -p no:cacheprovider tests/rag`;
- the full suite with `--ignore=tests/lakebase`;
- both with pyspark hidden.

LF line endings only. Don't touch `.agents/dispatch.sh`. Write
`.agents/mimo/VERDICT-rag-eval-harness-round6.md`.
