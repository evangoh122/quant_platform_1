# VERDICT: post-merge-round6 — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
(none — all issues fixed in this round)

## Changes made

### `agent/tools_retrieval.py`
- Added `from api.services.exceptions import EmbeddingConfigError` import (line 21).
- Added `except EmbeddingConfigError` handler before `except CorpusUnavailableError` (line 122-134).
  - Returns `"error": "retrieval_unavailable"` with `"reason": "embedding_config"`.
  - Uses a safe hardcoded message naming `EMBEDDING_PROVIDER`, `HF_TOKEN`, `HUGGINGFACEHUB_API_TOKEN` — never passes through `str(e)`, preventing secret leakage.
  - The generic corpus message ("Check Delta table connectivity") now only fires for real `CorpusUnavailableError` (Delta/corpus load failures).

### `tests/rag/test_hybrid_retriever.py`
- **Line 2073**: Replaced `assert "HF_TOKEN" in msg or "SEC filing corpus" in msg` with two strict assertions: `HF_TOKEN` present AND `"SEC filing corpus"` absent. The `or` was passing for the wrong reason.
- **Line 2322**: Same fix — replaced `or` assertion with strict presence/absence checks.
- **New test `test_token_value_never_leaks_in_message`** (line 2328): Verifies that a secret token value injected into an `EmbeddingConfigError` message never appears in the `search_sec_filings` response message.

## Non-blocking notes
- The `reason: "embedding_config"` field is new and downstream consumers could use it for structured error handling, but no existing code depends on it yet.
- The safe message is generic; if future `EmbeddingConfigError` variants need distinct user-facing text, the handler may need refinement.

## Checks run
- `python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py` → **303 passed, 19 skipped** (full suite, with pyspark)
- New/changed tests verified to **fail on HEAD before fix** (2 FAILED: `test_hf_no_token_search_sec_filings_returns_unavailable`, `test_missing_token_returns_retrieval_unavailable`) and **pass after fix** (3 passed including `test_token_value_never_leaks_in_message`).
- LF line endings confirmed via `file` command.
- No scratch files in repo (`git status` shows only the 2 modified files).
- Commit: `df1deaf` on branch `fix/post-merge-coderabbit`.