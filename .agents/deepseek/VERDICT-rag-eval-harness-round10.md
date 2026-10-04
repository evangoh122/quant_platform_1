# VERDICT: rag-eval-harness-round10 — DeepSeek (checker)
===VERDICT START===
Status: CHANGES_REQUESTED
Round: 10

Checker: DeepSeek. Scope: cfe2f90..HEAD. Read-only; mutation proofs run in /tmp copies.

## Test counts (Linux, /tmp/h8-venv, Python 3.12.13, pytest 9.1.1)
- `python -m pytest tests/rag -q` → 418 passed, 19 skipped, 0 failed (39s).
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python -m pytest tests/rag -q` → 418 passed, 19 skipped, 0 failed (36s).
- No "Unknown config option: timeout" warning in either run (pytest-timeout loaded; `timeout = 30` honoured).

## Blocking findings
1. [tests/rag/conftest.py:91-93] Item 3's requested regression test is missing. The scoping fix itself is present and correct (save `_prev_timeout`, `socket.setdefaulttimeout(10)`, `request.addfinalizer` restore), and I confirmed via direct fixture execution that the finalizer restores the previous value (`None → 10 → None`). But the build request explicitly required "Test: after the guard fixture, `socket.getdefaulttimeout()` equals its previous value." No such test exists anywhere under `tests/` (grep for `getdefaulttimeout`/`setdefaulttimeout`/`scoping` matches only `tests/rag/conftest.py`). MiMo's self-verdict cites a `timeout_scoping_proof.py`, but that file is not present in the repo (and a standalone proof script is not a committed pytest test). Without a committed test, the global-state leak fix can silently regress.

## Verified (non-blocking status for these items)
Item 1 — DONE. `tests/rag/test_rag_eval_retrieval.py:254-257` builds `prod_seq` from `results_prod` (the wrapper's RETURN VALUE) via `r.get("chunk_id")` / `r.get("rerank_score")`, not from captured tuples inside the fake reranker. `agent/tools_retrieval.py:113` now exposes `rerank_score` in the returned dict. Mutation proof (in /tmp copy): perturb ONLY the wrapper output dicts' `rerank_score` ×1.01 → the test FAILS with the score assertion:
`AssertionError: Score mismatch at position 0 (chunk smoke-001): harness=0.79 vs prod=0.7979` (`assert 0.79 == 0.7979 ± 8.0e-10`). Full mutated suite: 1 failed (this test), 417 passed, 19 skipped — the mutation is caught only by the intended test.

Item 2 — DONE. `pytest-timeout` added to `.github/workflows/ci.yml:44` and `requirements.txt:18` (`pytest-timeout>=2.2.0`). `pytest.ini` `timeout = 30` is honoured: `--timeout` appears in `pytest --help`; with `-p no:timeout` the plugin is confirmed loaded because the "Unknown config option: timeout" PytestConfigWarning appears only when the plugin is disabled.

Item 4 — DONE. `tests/rag/_netguard.py` extracts the real `_is_loopback` (ipaddress-based); `tests/rag/conftest.py:7` and `tests/rag/test_network_guard.py:176,182,188` both import it — the tests no longer test a local copy. Mutation proof (in /tmp copy): change the real function to block `127.0.0.2` (`... and host != "127.0.0.2"`) → `test_loopback_127_0_0_2_allowed` FAILS (`assert False is True`, tests/rag/test_network_guard.py:178).

No test deleted or weakened (git diff cfe2f90..HEAD -- tests): removed lines are only the three local `_is_loopback` copies (replaced by real-function import) and the `_prod_reranked_docs` capture scaffolding (replaced by return-value comparison). The score assertion was strengthened (return-value source), not weakened.

## Non-blocking notes
- `tests/rag/_netguard.py` has no trailing newline.
- `test_search_sec_filings_matches_hybrid_rerank` times out (>30s) when run in isolation because the dense-embedding load hits the network guard with HF retries; in the full suite it is fast (embeddings warm). This is pre-existing (present in round 9), not a round-10 regression, and it incidentally demonstrates pytest-timeout (30s) actually fires.

## Checks run
- `python -m pytest tests/rag -q` → pass (418 passed, 19 skipped).
- `PYTHONPATH=.../scratchpad/nps python -m pytest tests/rag -q` → pass (418 passed, 19 skipped).
- `python -m pytest --help | grep -i timeout` → `--timeout` registered; no unknown-option warning.
- `python -m pytest tests/rag -q -p no:timeout` → "Unknown config option: timeout" (proves plugin was loaded in normal run).
- Mutation A (wrapper output score ×1.01, /tmp/rag-eval-harness-round10-mut-wrapper) → target test FAILS (score mismatch).
- Mutation B (_is_loopback blocks 127.0.0.2, /tmp/rag-eval-harness-round10-mut-netguard) → target test FAILS (`assert False is True`).
- Socket-timeout restoration, direct fixture execution (/tmp): `None → 10 → None`, finalizer restores correctly.
===VERDICT END===
