# VERDICT: rag-eval-harness round 9 — MiMo
**Status:** APPROVED
**Round:** 9

## Blocking findings
None.

## Non-blocking notes
- 2 pre-existing dense-mode failures (`test_eight_configs_produce_results`, `test_pit_filter_applied_in_dense`) — require network to load SentenceTransformer model. Not introduced by this round.
- pyspark hidden path (`/tmp/claude-1000/.../nps`) does not exist on this machine. Tests pass without it (pyspark stubs installed via conftest `fake_pyspark` fixture).

## Checks run
- `python -m pytest tests/rag/test_rag_eval_retrieval.py tests/rag/test_rag_eval_report.py tests/rag/test_network_guard.py -q --timeout=30` → 53 passed, 2 skipped (AF_UNIX on Windows), 2 failed (pre-existing dense-mode network dependency)
- `python -m pytest tests/rag/test_rag_eval_retrieval.py tests/rag/test_rag_eval_report.py tests/rag/test_network_guard.py -q --timeout=30 -k "not eight_configs and not pit_filter_applied_in_dense"` → 53 passed, 2 skipped, 0 failed

## Mutation proof (score perturbation)
Script at `/tmp/rag-mut-proof/test_mutation.py` — perturbs `rerank_score *= 1.01` in production path only:
```
=== Normal scores ===
  smoke-004: 0.94
  smoke-002: 0.93
  smoke-009-old: 0.75
  smoke-008: 0.46
  smoke-001: 0.18

=== Mutated scores (*= 1.01) ===
  smoke-004: 0.9493999999999999
  smoke-002: 0.9393
  smoke-009-old: 0.7575000000000001
  smoke-008: 0.4646
  smoke-001: 0.1818

=== Comparison (normal vs mutated) ===
EXPECTED FAIL: Score mismatch at pos 0 (chunk smoke-004): normal=0.94 vs mutated=0.9493999999999999

Mutation proof: test correctly detects score perturbation.
```

## Items completed
1. `TestProductionWrapperMatchesHarness` now compares `(chunk_id, score)` tuples with `pytest.approx(rel=1e-9)`. Captures rerank_score via `_prod_reranked_docs` in the fake reranker.
2. Restored exact-string assertion `report["cli_args"]["corpus"] == "relative/corpus.jsonl"` alongside Path check. Fixed `report.py` to normalize `\\` → `/` for Path objects.
3. Added `test_dict_keys_redacted_to_basename`: `{Path("/home/x/k.jsonl"): 1, "/tmp/a/b": 2}` → keys become `"k.jsonl"` and `"b"`.
4. `_is_loopback` uses `ipaddress.ip_address(host).is_loopback` with ValueError → only literal `"localhost"` accepted. Added tests: `127.1.evil.com` blocked, `127.0.0.2` and `::1` allowed.
5. Added `timeout = 30` to `pytest.ini` + `socket.setdefaulttimeout(10)` in `_block_network` fixture.