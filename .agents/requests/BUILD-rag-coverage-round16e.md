# BUILD-rag-coverage round 16e — IMPLEMENT NOW (Codex merge review: restore weakened tests; tests only)

You are MiMo. Fix `.agents/codex/VERDICT-rag-coverage-merge.md`. Tests only — production code is correct. Commit, LF endings, do not touch
`.agents/dispatch.sh`, mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`.
The merge weakened main's fallback tests in tests/rag/test_hybrid_retriever.py:
- :~1356 claims to verify PIT filtering but has no future row and never asserts the `as_of` predicate. Restore main-parent strength
  (`git show 5ba57e4^2:tests/rag/test_hybrid_retriever.py`): a fake silver_sec_sections frame with one row accepted BEFORE and one AFTER `as_of`;
  assert the after-row is excluded and that the ticker AND as_of `.where(...)` filters are applied.
- :~1300 no longer checks the successful fallback output contract. Restore a SUCCESSFUL-fallback test asserting every mapped field
  (chunk_id, accession_number, form_type, accepted_ts, source_url, ticker, section, chunk_index, chunk_text, retrieval_mode="substring_fallback",
  _warning="hybrid_retrieval_failed"). Keep the failure-path test as a separate test.
Mutations that must FAIL (record in verdict): remove the fallback PIT predicate (agent/tools_retrieval.py:~161); drop `source_url` from fallback
output (:~187). Run: python3 -m pytest tests/rag tests/bronze -q. Verdict: .agents/mimo/VERDICT-rag-coverage-round16e.md.
