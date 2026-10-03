===VERDICT START===
# VERDICT: rag-ci-nopyspark — DeepSeek (independent checker)
**Status:** APPROVED
**Round:** 1

Checker verdict: read-only. I reviewed MiMo's commit `29376da` and ran the
mutation/leak checks in `/tmp` copies only — the worktree was never edited
(all scratch under `/tmp/nopyspark`, `/tmp/qp1-rag-mut`, `/tmp/qp1-rag-mut2`).

## Answers to the three check questions

### 1. Production code unchanged? — YES
- `git diff HEAD~3 -- agent api pipelines` → empty (0 lines).
- `git show 29376da --stat` touches only `tests/rag/conftest.py`,
  `tests/rag/test_hybrid_retriever.py`, and the MiMo verdict markdown. No
  production module is modified by the fix commit.

### 2. Does the fake stub still verify real behaviour? — YES (all three mutations caught)
The `_ColExpr` stub is permissive (comparisons return `self`, `__getattr__`
returns `self`), so the only way to prove the tests are not passing trivially
is mutation. Each of the three mutations was applied to a `/tmp` copy of the
repo and run under `PYTHONPATH=/tmp/nopyspark`, whose `sitecustomize.py` sets
`sys.modules["pyspark*"] = None` so the fixture is the active pyspark provider.

- **Remove fallback `as_of` filter** (`agent/tools_retrieval.py:138-144`) →
  `test_fallback_as_of_filters_future_filings` **FAILS**:
  `AssertionError: Expected at least 2 where calls (ticker + as_of), got 1`.
- **Remove `unix_timestamp` epoch in `_load_corpus`** (`api/services/hybrid_retriever.py:270`
  + the `accepted_epoch` read at `:298-304`, faithfully reverting `4bd5aff`) →
  `test_load_corpus_uses_epoch` **FAILS**:
  `AssertionError: Expected UTC ISO string, got: ''`.
- **Break idempotency anti-join** (`pipelines/build_sec_embeddings.py:91`
  `new_rows = [r for r in all_rows if ...]` → `list(all_rows)`) →
  `TestEmbeddingBuildIdempotency` **FAILS 2**: `test_second_run_writes_zero_rows`
  and `test_real_idempotency_count` (`assert 5 == 3`).

Each mutation fails at least one test, so the stub does not make the filters
pass trivially.

### 3. Does the fixture leak when real pyspark is installed? — NO
- `python3 -m pytest -q tests/rag` → **264 passed, 19 skipped** (real pyspark).
- `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/rag` → **264 passed, 19 skipped**.
- `python3 -m pytest -q tests` (full suite, real pyspark) → **592 passed, 67 skipped,
  2 failed, 22 errors**. All 2 failures + 22 errors are in `tests/lakebase/` and
  are a disabled Lakebase/Postgres endpoint (`ep-steep-truth-d1ex36nr.database…
  "The endpoint has been disabled. Enable it using the API and retry."`), i.e.
  environmental and unrelated to this commit. The fixture is function-scoped
  (`monkeypatch.setitem(sys.modules, …)`, auto-reverted), lives in
  `tests/rag/conftest.py` (only loaded for `tests/rag/`), and is only applied to
  tests that explicitly request it — it cannot affect `tests/lakebase/` or any
  other module.

## Non-blocking notes

- [tests/rag/test_hybrid_retriever.py:993-1063] `test_load_corpus_uses_epoch`
  mocks the collect row to supply `accepted_epoch` directly and never asserts
  what `select(...)` was passed. It therefore verifies the *epoch→ISO conversion*
  and catches a full revert of the round-6 fix (read key changes to
  `accepted_ts`, which the mock lacks → `''`), but it would **not** catch a
  narrower regression such as swapping `F.unix_timestamp(...)` for
  `F.col("accepted_ts").alias("accepted_epoch")`. Non-blocking because the
  realistic regression (the `4bd5aff` revert) is caught; flagging only for
  future hardening of that one assertion.
- [tests/rag/conftest.py:57-73] `_ColExpr.__eq__`/`__ne__` returning `self` means
  `F.col("x") == "val"` is a truthy object. The tests that matter assert on
  `where()` call counts / row-write counts, not on filter boolean results, so
  this is safe today — but any future test that does `assert df.where(...).count()`
  semantics would silently pass. Keep assertions structural (call counts, output
  rows) rather than value-based under the stub.

## Checks run

```
$ git diff HEAD~3 -- agent api pipelines          # empty
$ git show 29376da --stat                         # only tests/rag/* + .agents/mimo/VERDICT-...
```

```
$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q \
    tests/rag/test_hybrid_retriever.py::TestSearchSecFilingsError::test_fallback_as_of_filters_future_filings
1 failed in 0.53s   (mutation: as_of filter removed)

$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q \
    tests/rag/test_hybrid_retriever.py::TestAcceptedEpochTimezoneSafe::test_load_corpus_uses_epoch
1 failed in 0.46s   (mutation: unix_timestamp epoch reverted)

$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q \
    tests/rag/test_hybrid_retriever.py::TestEmbeddingBuildIdempotency
2 failed, 2 passed in 0.46s   (mutation: anti-join broken)
```

```
$ python3 -m pytest -q tests/rag                   # 264 passed, 19 skipped
$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/rag   # 264 passed, 19 skipped
$ python3 -m pytest -q tests                       # 592 passed, 67 skipped, 2 failed, 22 errors (all lakebase/psycopg)
```
===VERDICT END===
