# BUILD: rag CI fix, tests must not need pyspark (MiMo)

PR #18's CI fails with 8 tests in `tests/rag/test_hybrid_retriever.py`. The GitHub runner
has no `pyspark`. Rounds 5–7 added `from pyspark.sql import functions as F` inside
`_load_corpus`, `build_sec_embeddings.build`, and the `search_sec_filings` fallback. Locally,
databricks-connect provides pyspark, so the tests passed here and failed in CI.

Failing tests:
- TestEmbeddingBuildIdempotency (4 tests)
- TestAcceptedEpochTimezoneSafe::test_load_corpus_uses_epoch
- TestSearchSecFilingsError::test_fallback_results_tagged_with_retrieval_mode
- TestSearchSecFilingsError::test_fallback_as_of_filters_future_filings
- TestSearchSecFilingsError::test_fallback_output_keys_match_hybrid_path

## Reproduce locally (hides pyspark the way CI does)
    mkdir -p /tmp/nopyspark && printf 'import sys\nfor m in ("pyspark","pyspark.sql","pyspark.sql.functions","pyspark.sql.types"):\n    sys.modules[m]=None\n' > /tmp/nopyspark/sitecustomize.py
    PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/rag/test_hybrid_retriever.py   # today: 8 failed

## Fix: tests only. Do NOT change production code.
These tests already mock Spark, so they should also provide a fake `pyspark.sql.functions`.
Add a pytest fixture, e.g. `fake_pyspark` in `tests/rag/conftest.py`. With `monkeypatch.setitem(sys.modules, ...)`,
it installs stub modules `pyspark`, `pyspark.sql`, `pyspark.sql.functions`, and `pyspark.sql.types`
if needed. The stubs return column-expression objects your existing fake DataFrames understand:
`col`, `lit`, `lower`, `unix_timestamp`, `.alias`, `.contains`, `<=`, `.desc`.
Use the fixture in the 8 failing tests.

Do NOT use `importorskip` for these tests. They are the point-in-time and idempotency
guards, so they must run in CI.

## Acceptance
- Both commands pass:
  - `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/rag`
  - `python3 -m pytest -q tests/rag` (real pyspark present)
- Mutation check, still valid without pyspark: in a /tmp copy, remove the `as_of` filter
  from the fallback in `agent/tools_retrieval.py`. `test_fallback_as_of_filters_future_filings`
  must fail under `PYTHONPATH=/tmp/nopyspark`. Paste the output in the verdict.
- LF line endings. Don't touch `.agents/dispatch.sh`. Commit. Write
  `.agents/mimo/VERDICT-rag-ci-nopyspark.md`.
