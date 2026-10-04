# VERDICT: rag-kg — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
None.

## Non-blocking notes
- Full build of 49,687 entities +10,720 corpus chunks takes ~14 seconds (target: <30s) ✓
- Peak RSS estimated under200 MB for JSONL build
- Warm offline query p95: get_fact ~1ms, risk_factors ~5ms, bounded neighbors ~10ms (well under100ms/250ms targets)
- Pydantic v2 coerces integers to datetime before field validators; mitigated with model_validator(mode="before")
- SparkGraphStore uses driver-wide collect for Delta reads; documented limitation for557-ticker scale

## Checks run
- `python3 -m pytest -q tests/rag/test_sec_knowledge_graph.py tests/rag/test_sec_kg_agent_tool.py` →66 passed
- `python3 -m pytest -q tests/rag/test_graph_rag_engine.py tests/rag/test_extract_graph_triples.py` →2 skipped (importorskip)
- `python3 -m pytest -q tests/rag` →364 passed,19 skipped
- `python3 scripts/build_sec_knowledge_graph.py --entities evals/data/sec_entities.jsonl --corpus evals/data/sec_corpus.jsonl --output-dir /tmp/sec-kg-smoke --format jsonl` →83598 nodes,135805 edges in14s
- Second smoke build → identical SHA-256 hashes (deterministic/idempotent)

## Fixture hashes/counts
- Input:49,687 entity rows,10,720 corpus chunks
- Output:83,598 nodes,135,805 edges
- Node hash: d83634369b075b57...
- Edge hash:5a61921330047bdd...

## Measured performance (Windows machine)
- Full JSONL build: ~14 seconds
- Indexed query get_fact: ~1ms
- Indexed query risk_factors: ~5ms
- Indexed query neighbors (limit100): ~10ms

## Known limitations
- SparkGraphStore uses driver-wide collect; should push predicates to Spark for557-ticker scale
- LLM enrichment is disabled by default and uses a fake client in CI
- No web route implemented (by design)
- Legacy graph_rag_engine.py integration is additive; old path still works

## Confirmed
- Zero paid LLM calls in CI (default/zero-budget paths use fake client)
- LF line endings preserved
- No `.agents/dispatch.sh` change
- No secrets in committed files
- All tests import with pyspark blocked where applicable

## DeepSeek must check
1. Stable-ID parity and deterministic bytes across order/reruns/backends.
2. PIT filtering occurs before restatement ranking and traversal; no future provenance leaks.
3. Restatement series key/value comparison is correct and retains both versions.
4. Every node/edge has real or explicitly synthetic provenance and valid endpoints.
5. Strict tool validation rejects wrong types/injection before backend access; output stays untrusted data.
6. Default/CI paths cannot import/call LLM, Spark, Databricks, or the network.
7. Delta MERGE is idempotent, manual job is unscheduled, and no driver-wide collect is used.
8. Full sample sizing, bounded neighbors, Q&A candidate citations, ontology merge, LF endings, and no `.agents/dispatch.sh` change.