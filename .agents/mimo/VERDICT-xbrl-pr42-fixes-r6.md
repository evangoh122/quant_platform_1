# VERDICT: xbrl-pr42-fixes-r6 — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
(none)

## Non-blocking notes
- All 4 new focused tests pass; mutation proof confirmed for both writers.
- No production code modified; test-only change as specified.

## Checks run

```
python3 -m pytest -q tests/test_jobs_serverless.py → 16 passed
python3 -m pytest -q tests/bronze/test_sec_companyfacts.py → 98 passed (4 new)
python3 -m pytest -q -m "not spark and not lakebase and not databricks" → 2672 passed, 107 skipped
git diff --check → clean (no whitespace issues)
```

## New tests added

`TestDefaultWriterUsesSharedRuntime` in `tests/bronze/test_sec_companyfacts.py`:

| Test | What it proves |
|------|---------------|
| `test_facts_writer_default_calls_get_spark` | `SparkCompanyFactsWriter()` with no `spark_factory` calls `get_spark()` and returns its result |
| `test_manifest_writer_default_calls_get_spark` | `SparkCompanyFactsManifestWriter()` with no `spark_factory` calls `get_spark()` and returns its result |
| `test_facts_writer_explicit_factory_takes_precedence` | Explicit `spark_factory` is used instead of `get_spark()` |
| `test_manifest_writer_explicit_factory_takes_precedence` | Explicit `spark_factory` is used instead of `get_spark()` |

## Mutation proof

In a fresh `git archive` copy under `/tmp`:

1. **SparkCompanyFactsWriter**: replaced `return get_spark()` with `SparkSession.builder.getOrCreate()` → `test_facts_writer_default_calls_get_spark` **FAILED** (RuntimeError: Only remote Spark sessions...)
2. **SparkCompanyFactsManifestWriter**: replaced `return get_spark()` with `SparkSession.builder.getOrCreate()` → `test_manifest_writer_default_calls_get_spark` **FAILED** (RuntimeError: Only remote Spark sessions...)

Both mutation failures confirm the tests detect bypass of the shared runtime helper.