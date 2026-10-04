===VERDICT START===
# VERDICT: rag-eval-harness (round 5 re-check) — DeepSeek
**Status:** APPROVED
**Round:** CHECK 2 (HEAD 57d4190, branch `slice/rag-eval-harness`)

## Summary

Round 5 resolves my prior blocking finding. The `-1` leakage sentinel is gone
(`count_pit_leakage()` in `retrieve.py:101-128` returns the real count + leaked
IDs), the gate is computed *before* the report is written (`cli.py:248-256`), and
the report/exit-code status now derive from the same source. I reproduced Claude's
mutation run byte-for-byte and verified both gate outcomes end-to-end.

## Blocking findings

None.

## Verification of the round-5 re-check items

1. **My finding is fixed.** `retrieve.py:186-190` now attaches `leak_count` /
   `leaked_chunk_ids` to the ValueError, and `run_retrieval` reads them via
   `getattr(e, "leak_count", 0)` instead of `-1`. `cli.py:230-240` sums real
   counts and collects per-config leaked IDs. `report.py:70-88` renders the
   `status` field and a truncated leaked-ID table. **Mutation proof** (identity
   `_pit_filter`, fixture, all modes, both filters) reproduced exactly:
   `exit 1`, JSON `pit_leakage_total: 30`, `status: FAIL`,
   `pit_leakage_by_config` = {bm25:10, hybrid_rrf:10, hybrid_rerank:10},
   Markdown `**Total leakage: 30** FAIL` with **no PASS** and a populated
   `leaked_chunk_ids_by_config`. Matches Claude's expected result verbatim.

2. **No code path renders PASS with leakage or errors.** In `cli.py` the single
   assignment `pit_status` (lines 252-256) drives both the report `status` field
   and the exit code (lines 324-331). Leakage → `FAIL`, else errors → `INCOMPLETE`,
   else `PASS`. The report is written after `pit_status` is set (`cli.py:258-294`),
   and the Markdown PIT gate uses `report["status"]` directly (`report.py:73-75`).
   The old dead branch (`if pit_leakage_total > 0: return 1` after report write)
   is gone. (See non-blocking note 1 for the only theoretical gap.)

3. **INCOMPLETE vs FAIL precedence.** `cli.py:252-256` is `FAIL (leakage) > INCOMPLETE
   (errors) > PASS`. Verified both branches end-to-end: leakage → `FAIL` (above); a
   wrong-model sidecar (30 `Embedding model mismatch` errors, 0 leakage) →
   `pit_leakage_total: 0`, `status: INCOMPLETE`, summary prints `PIT Leakage: 0
   INCOMPLETE`, `exit 1`. Leakage is the hard gate and wins over error-count, as
   BUILD item 6 requires.

4. **Other check items re-run — still pass.**
   - PIT gate real: `accepted_epoch` → ISO UTC (`corpus.py:24-52`), missing/unparseable
     timestamp = violation (`retrieve.py:113-127`, `test_rag_eval_round3.py:26-92,106-160`).
   - Real retrieval path: `retrieve_mode` reuses `bm25_search`/`vector_search`/
     `rrf_fuse`/`rerank` (`hybrid_retriever.py:683-790`); parity test
     `test_retrieve_matches_hybrid_rerank_mode` asserts `retrieve()` and
     `retrieve_mode("hybrid_rerank")` agree (`test_rag_eval_retrieval.py:241-284`).
   - Model-mismatch check NOT disabled: probe forcing `_stored_embedding_model =
     "totally/different-model-v99"` → `CorpusUnavailableError: Embedding model mismatch`
     (`hybrid_retriever.py:534-545`). Sidecar model/dim reach the retriever via
     `install_offline_corpus` (`corpus.py:416-420`).
   - Stale scripts retired: `evals/run_eval.py` / `evals/ragas_eval.py` deleted;
     `grep -rn 'run_eval\|ragas_eval\|auditable-rag' --include='*.py'` → no matches.
   - Test isolation: `tests/rag/conftest.py:34-70` resets embedding + retriever
     singletons before/after each test.

## Non-blocking notes

- [evals/rag_eval/report.py:74] `render_markdown`'s fallback
  `status if status else ("PASS" if pit_total == 0 else "FAIL")` ignores `errors`
  when `status` is empty — a hand-built `RunReport(errors=[...])` would render
  "PASS". Unreachable via the CLI (which always sets `status`), but the fallback
  should also consider `errors` to fully satisfy "no code path renders PASS with
  errors".
- [tests/rag/test_rag_eval_round4.py:187-224] `test_pit_incomplete_on_errors` /
  `test_pit_fail_when_leakage` inline the *old* precedence (INCOMPLETE before FAIL)
  and test only a local copy, not `cli.py`. There is no end-to-end test asserting the
  report's `status == "INCOMPLETE"` through the CLI; the FAIL path is covered by
  `test_rag_eval_round5.py`, but the INCOMPLETE path is only proven by my manual probe.
- [api/services/hybrid_retriever.py:555-558] `vector_search` still re-implements the
  PIT filter inline rather than calling `_pit_filter`, so mutating `_pit_filter` only
  disables BM25/hybrid (not dense) — which is why the mutation yields 30 (not 40)
  leaked evaluations. The harness gate is unaffected (it scores returned hits), but
  this duplicated/divergent filter is worth consolidating.

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/rag` → **384 passed, 19 skipped**.
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → **663 passed, 67 skipped**.
- Mutation (`_pit_filter` → identity, fixture, all modes, both filters) → `exit 1`,
  `pit_leakage_total 30`, `status FAIL`, Markdown FAIL, no PASS.
- Wrong-model sidecar (errors-only) → `exit 1`, `status INCOMPLETE`, `pit_leakage_total 0`.
- Model-mismatch probe → `CorpusUnavailableError` (check not disabled).
- `grep` for `run_eval`/`ragas_eval`/`auditable-rag` → no matches.
- `git status` → working tree clean.
===VERDICT END===
