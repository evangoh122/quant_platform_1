"""evals/rag_eval — SEC RAG retrieval evaluation harness.

Deterministic retrieval metrics over the production hybrid BM25 + dense + RRF
pipeline.  No LLM calls in retrieval mode.  Generation judging is phase 2
behind an explicit ``--generation`` flag and is never enabled in CI.

Offline adapter loads corpus from JSONL + optional .npz embedding sidecar.
Live adapter loads from Delta tables.
"""