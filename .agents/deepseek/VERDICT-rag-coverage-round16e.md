# VERDICT: rag-coverage round 16e — DeepSeek
**Status:** APPROVED
**Round:** 16e

## Blocking findings
None.

## Non-blocking notes
- `test_fallback_as_of_filters_future_filings` (tests/rag/test_hybrid_retriever.py:1392) is now
  *stronger* than the main parent: it retains main's `where_calls >= 2` assertion (line 1466) and
  adds `ts_calls` + `lit_args` checks (lines 1461–1464) so the predicate itself
  (`unix_timestamp(accepted_ts) <= lit(as_of_epoch)`) is asserted, not merely the call count.
- The trailing `as_of=None` second invocation (lines 1470–1483) is cosmetic dead weight — its
  result is unused — but it is inherited verbatim from the main parent and is not a defect.

## Verification of requested mutations (independent archive copies)

Mutation "PIT predicate → lit(True)" — replaced `agent/tools_retrieval.py:166`
`F.unix_timestamp(F.col("accepted_ts")) <= F.lit(as_of_epoch)` with `F.lit(True)`:

```
FAILED tests/rag/test_hybrid_retriever.py::TestSearchSecFilingsError::test_fallback_as_of_filters_future_filings
1 failed, 1127 passed, 36 skipped
> assert ts_calls, "fallback must build unix_timestamp(accepted_ts) for the PIT filter"
```

Mutation "drop source_url from fallback output" — removed `agent/tools_retrieval.py:187`:

```
FAILED tests/rag/test_hybrid_retriever.py::TestSearchSecFilingsError::test_fallback_output_keys_match_hybrid_path
1 failed, 1127 passed, 36 skipped
> Key mismatch: missing={'source_url'}
```

Both mutations are caught by exactly one test each, confirming the restored assertions are
load-bearing against the production fallback code.

## Main-parent strength comparison
- `test_fallback_output_keys_match_hybrid_path`: current (tests/rag/test_hybrid_retriever.py:1300)
  is identical to `git show 5ba57e4^2:tests/rag/test_hybrid_retriever.py` — full key set
  `{chunk_id, accession_number, form_type, accepted_ts, source_url, ticker, section, chunk_index,
  chunk_text, retrieval_mode, _warning}` plus per-field value mapping.
- `test_fallback_as_of_filters_future_filings`: current ≥ main parent (superset of assertions).

## Scope check — nothing else changed
`git diff --name-status 5f2598d HEAD` (Codex review point → HEAD) shows only:
- `M tests/rag/test_hybrid_retriever.py`
- `A .agents/mimo/VERDICT-rag-coverage-round16e.md`
- `A .agents/requests/CHECK-rag-coverage-round16e.md`

No production code (`agent/`, `api/`, `db/`, etc.) changed. Worktree clean.

## Checks run
- `python3 -m pytest tests/rag tests/bronze -q` → **1128 passed, 36 skipped, 10 warnings**
- Mutation 1 (PIT → `lit(True)`) full suite → **1 failed, 1127 passed, 36 skipped**
- Mutation 2 (drop `source_url`) full suite → **1 failed, 1127 passed, 36 skipped**
