# VERDICT: rag-eval-harness-round5 — MiMo
**Status:** APPROVED
**Round:** 5

## Blocking findings
- None remaining. All four defects from the BUILD request are fixed.

## Fixes applied

1. **`evals/rag_eval/retrieve.py`** — Added `count_pit_leakage()` (returns real count + leaked chunk IDs without raising). Refactored `assert_no_pit_leakage()` to use it and attach `leak_count`/`leaked_chunk_ids` to the ValueError. Modified `run_retrieval()` to extract the real count from the exception via `getattr(e, "leak_count", 0)` — the `-1` sentinel is eliminated.

2. **`evals/rag_eval/cli.py`** — Gate computation moved BEFORE report write. `pit_status` now prioritizes leakage (FAIL) over errors (INCOMPLETE). Added `leaked_chunk_ids_by_config` collection and `errors_list` population. Report is built with `status`, `errors`, and `leaked_chunk_ids_by_config` fields populated.

3. **`evals/rag_eval/models.py`** — Added `leaked_chunk_ids: list[str]` to `ItemResult`. Added `leaked_chunk_ids_by_config: dict[str, list[str]]` and `status: str` to `RunReport`.

4. **`evals/rag_eval/report.py`** — PIT gate section now renders `status` field and includes per-config leaked chunk IDs (truncated to 20). Per-item rows include `leaked_chunk_ids`. Errors section was already present.

## Non-blocking notes
- The gate precedence is now: FAIL (leakage > 0) > INCOMPLETE (errors) > PASS. This matches the BUILD requirement that leakage is the hard gate.
- `count_pit_leakage()` is a reusable pure function — no side effects, no raising.

## Checks run
- `python3 -m pytest -q -p no:cacheprovider tests/rag` → **384 passed, 19 skipped**
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → **663 passed, 67 skipped**
- `grep -cP '\r' evals/rag_eval/retrieve.py evals/rag_eval/cli.py evals/rag_eval/models.py evals/rag_eval/report.py tests/rag/test_rag_eval_round5.py` → all 0 (LF only)
- `.agents/dispatch.sh` not touched